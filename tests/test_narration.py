"""Mock the documented Responses API; never send credentials or paid live calls."""

import json
from dataclasses import replace
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.analysis import WeeklyComparison
from src.config import Settings, load_settings
from src.models import WeeklyData
from src.narration import narrate
from src.scoring import WeeklyScore
from src import reporting


@pytest.fixture
def context(report_inputs, tmp_path):
    settings = Settings(data_dir=tmp_path, research_dir=tmp_path, reports_dir=tmp_path,
                        timezone=ZoneInfo('Pacific/Auckland'), llm_provider='openai',
                        llm_api_key='test-secret-never-log', llm_model='gpt-4.1-mini-2025-04-14')
    return (settings, WeeklyData.model_validate_json(report_inputs[0].read_bytes()),
            WeeklyComparison.model_validate_json(report_inputs[1].read_bytes()),
            WeeklyScore.model_validate_json(report_inputs[2].read_bytes()))


def response(text='National context alone cannot establish graduate hiring prospects.', ids=None):
    return {'id': 'resp_fixture', 'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({
            'insights': [{'text': text, 'fact_ids': ids if ids is not None else ['F1']}]})}]}]}


def test_request_contract_and_valid_interpretation(context, report_inputs, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == 'Bearer test-secret-never-log'
        body = json.loads(request.content)
        assert body['store'] is False and body['max_output_tokens'] == 1200
        assert body['text']['format']['strict'] is True
        assert 'Do not invent' in body['instructions']
        assert 'tools' not in body and 'test-secret' not in request.content.decode()
        payload = json.loads(body['input'])
        assert payload['facts'][0]['id'] == 'F1'
        assert 'evidence' not in payload['facts'][0] and 'source_url' not in payload['facts'][0]
        assert payload['overall_index'] is None
        return httpx.Response(200, json=response())

    result = narrate(*context, transport=httpx.MockTransport(handler))
    assert len(calls) == 1 and result.status == 'generated'
    assert result.request_sha256 and result.response_id == 'resp_fixture'
    assert 'test-secret' not in json.dumps(result.audit())
    monkeypatch.setattr(reporting, 'narrate', lambda *args: result)
    report = reporting.build_report(*report_inputs, context[0])
    assert 'LLM Interpretation — Review Required' in report.content
    assert 'insufficient evidence for all six components' in report.content
    assert result.insights[0].text in report.content


@pytest.mark.parametrize('status', [401, 403, 429, 500, 302])
def test_provider_errors_do_not_retry_or_leak_bodies(context, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text='test-secret-never-log', headers={'Location': 'https://evil.example/'})

    result = narrate(*context, transport=httpx.MockTransport(handler))
    assert result.status == 'fallback' and len(calls) == 1
    assert str(status) in result.reason
    assert 'test-secret' not in json.dumps(result.audit())


@pytest.mark.parametrize('exception', [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failures_are_sanitised(context, exception):
    def handler(request):
        raise exception('test-secret-never-log', request=request)
    result = narrate(*context, transport=httpx.MockTransport(handler))
    assert result.status == 'fallback'
    assert 'test-secret' not in json.dumps(result.audit())


@pytest.mark.parametrize('payload', [
    response(ids=['F999']), response(ids=[]), response(text='Unemployment is 5.6%.'),
    response(text='Visit https://evil.example/'), response(text='<script>bad</script>'),
    {'status': 'incomplete', 'output': []}, {'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'No'}]}]},
    {'status': 'completed', 'output': None}, [],
])
def test_invalid_prose_refusals_and_malformed_responses_fall_back(context, payload):
    result = narrate(*context, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    assert result.status == 'fallback' and not result.insights


@pytest.mark.parametrize('body', ['not json', 'x' * 100_001])
def test_response_size_and_json_limits(context, body):
    result = narrate(*context, transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body)))
    assert result.status == 'fallback'


@pytest.mark.parametrize('changes,status', [({'llm_provider': 'none'}, 'disabled'),
                                            ({'llm_api_key': ''}, 'fallback'),
                                            ({'llm_model': ''}, 'fallback')])
def test_missing_configuration_makes_no_network_call(context, changes, status):
    settings, *inputs = context
    result = narrate(replace(settings, **changes), *inputs)
    assert result.status == status


@pytest.mark.parametrize('value', ['0', '-1', '121', 'nan', 'inf', 'invalid'])
def test_invalid_llm_timeout(monkeypatch, value):
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError, match='LLM_TIMEOUT_SECONDS'):
        load_settings()


def test_invalid_provider(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'unknown')
    with pytest.raises(ValueError, match='LLM_PROVIDER'):
        load_settings()
