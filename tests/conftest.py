"""All automated tests run without contacting live websites."""

import httpx
import pytest

from src import research


@pytest.fixture(autouse=True)
def offline_tests(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Live HTTP is not allowed in automated tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(research.time, "sleep", lambda seconds: None)
