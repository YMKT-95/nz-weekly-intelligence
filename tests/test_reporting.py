"""Reports preserve evidence semantics and survive unavailable history/services."""

import hashlib
import json
from dataclasses import replace

import pytest

from src import reporting
from src.analysis import compare_evidence
from src.reporting import build_report, save_report


def test_report_sections_citations_dates_and_missing_index(report_inputs):
    report = build_report(*report_inputs)
    text = report.content
    for section in ('Executive Summary', 'NZ Economy', 'NZ Labour Market', 'NZ IT Graduate Job Market',
                    'Global Context', 'NZX / Business Signals', 'Personal Job Search Index',
                    'What This Means for an IT Graduate', 'Recommended Actions'):
        assert section in text
    assert '5.6%' in text and '171,000 people' in text
    assert '+0.2 percentage points' in text and '+4.1%' in text
    assert '2026-06-01 to 2026-06-30' in text  # Lagged SEEK applications.
    assert 'publication: unknown' in text
    assert 'insufficient evidence for all six components' in text
    assert 'not confidence' in text and 'not a release date' in text
    assert 'No usable earlier weekly evidence' in text
    assert 'Index trend: unavailable' in text
    assert 'Graduate availability (20%): unavailable' in text
    assert report.narration['status'] == 'disabled'
    for i in range(1, 7):
        assert f'[F{i}]' in text and f'[F{i}]: <https://' in text
    assert hashlib.sha256(report_inputs[0].read_bytes()).hexdigest() in text


@pytest.mark.parametrize('target', [1, 2])
def test_mixed_run_or_hash_is_rejected(report_inputs, target):
    path = report_inputs[target]
    data = json.loads(path.read_text())
    data['current_file']['sha256'] = '0' * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='same evidence run'):
        build_report(*report_inputs)


@pytest.mark.parametrize('target', [1, 2])
def test_embedded_observation_tampering_is_rejected(report_inputs, target):
    path = report_inputs[target]
    data = json.loads(path.read_text())
    if target == 1:
        data['items'][0]['current'][0]['pointer'] = '/facts/999'
    else:
        component = next(c for c in data['components'] if c['status'] == 'scored')
        component['evidence'][0]['pointer'] = '/facts/999'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='observation does not match'):
        build_report(*report_inputs)


@pytest.mark.parametrize('kind', ['unchanged', 'revision', 'new_period', 'missing'])
def test_history_semantics_are_visible(report_inputs, tmp_path, kind):
    archive, comparison_path, _ = report_inputs
    old = json.loads(archive.read_text())
    old.update(report_week='2026-W36', week_start='2026-08-31', week_end='2026-09-06',
               collected_at='2026-09-06T12:00:00+12:00')
    for f in old['facts']:
        f['retrieved_at'] = old['collected_at']
        if f['metric'] == 'unemployment_rate':
            if kind in {'revision', 'new_period'}:
                f['value'] = 5.4
            if kind == 'new_period':
                f.update(period='March 2026 quarter', period_start='2026-01-01', period_end='2026-03-31')
    if kind == 'missing':
        # A synthetic earlier series that has disappeared from the current run.
        extra = dict(old['facts'][0], metric='previous_only_metric')
        old['facts'].append(extra)
    history = tmp_path / 'history'
    history.mkdir()
    (history / '2026-W36.json').write_text(json.dumps(old))
    comparison = compare_evidence(archive, history)
    comparison_path.write_text(comparison.model_dump_json())
    text = build_report(*report_inputs).content
    assert '2026-W36 (1 week(s) apart)' in text
    if kind == 'unchanged':
        assert 'Same observation collected again' in text
        assert 'Recorded difference:' not in text
    elif kind == 'revision':
        assert 'Same-period revision/correction' in text
        assert '+0.2 percentage points' in text
        assert 'Flagged for review' not in text
    elif kind == 'new_period':
        assert 'Later comparable data period' in text
        assert 'Flagged for review' in text
    else:
        assert 'Missing from this run; not zero' in text


def test_changed_historical_file_is_rejected(report_inputs, tmp_path):
    archive, comparison_path, _ = report_inputs
    data = json.loads(comparison_path.read_text())
    data['previous_file'] = {**data['current_file'], 'sha256': '0' * 64}
    comparison_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Historical evidence changed'):
        build_report(*report_inputs)


def test_source_text_cannot_inject_markdown_or_html():
    escaped = reporting._text('bad\n## heading <script> [link](https://evil.example)')
    assert '\n' not in escaped and '<script>' not in escaped
    assert '[link](' not in escaped and '\\#\\#' in escaped
    assert '%28' in reporting._link('source', 'https://example.com/a(b)')


def test_report_archive_and_atomic_weekly_view(report_inputs, tmp_path, monkeypatch):
    report = build_report(*report_inputs)
    directory = tmp_path / 'reports'
    archive, weekly = save_report(report, directory)
    assert archive.read_text() == weekly.read_text() == report.content
    audit = json.loads(archive.with_suffix('.json').read_text())
    assert audit['report_sha256'] == hashlib.sha256(report.content.encode()).hexdigest()
    with pytest.raises(FileExistsError):
        save_report(report, directory)
    newer = replace(report, run_name='new-run.md', content=report.content + '\nNew run\n')

    def fail(*args):
        raise OSError('Synthetic replace failure')

    monkeypatch.setattr(reporting.os, 'replace', fail)
    with pytest.raises(OSError):
        save_report(newer, directory)
    assert weekly.read_text() == report.content
    assert not list(directory.glob('.report-*.tmp'))
    assert (archive.parent / 'new-run.md').read_text() == newer.content


@pytest.mark.parametrize('changes', [{'run_name': '../escape.md'}, {'report_week': '../escape'},
                                     {'report_week': '2026-W99'}, {'content': ''}])
def test_invalid_output_names_are_rejected(report_inputs, tmp_path, changes):
    with pytest.raises(ValueError):
        save_report(replace(build_report(*report_inputs), **changes), tmp_path / 'reports')


def test_complete_synthetic_index_is_rendered_without_inventing_a_trend(report_inputs):
    # Synthetic component mappings test presentation, not live six-component coverage.
    score_path = report_inputs[2]
    card = json.loads(score_path.read_text())
    observed = next(c for c in card['components'] if c['status'] == 'scored')
    for component in card['components']:
        component.update(status='scored', score=5, rule={'synthetic': True},
                         evidence=observed['evidence'], data_age_days=observed['data_age_days'])
    card.update(status='complete', overall_score=5, covered_weight_percent=100)
    score_path.write_text(json.dumps(card))
    text = build_report(*report_inputs).content
    assert '**5.0 / 10 — provisional heuristic.**' in text
    assert 'Index trend: unavailable' in text
    assert 'Earlier index: unavailable' in text


def test_historical_score_hash_is_checked(report_inputs):
    score_path = report_inputs[2]
    card = json.loads(score_path.read_text())
    card['comparison']['previous_file'] = dict(path=str(score_path), sha256='0' * 64, report_week='2026-W37')
    score_path.write_text(json.dumps(card))
    with pytest.raises(ValueError, match='Historical scoring changed'):
        build_report(*report_inputs)
