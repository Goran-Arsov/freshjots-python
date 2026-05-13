"""Smoke tests — no network, just contract assertions."""
import pytest

from freshjots import ApiError, Client, __version__


def test_version_is_a_string():
    assert isinstance(__version__, str)


def test_client_requires_a_token(monkeypatch):
    monkeypatch.delenv("FRESHJOTS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="FRESHJOTS_TOKEN"):
        Client()


def test_client_accepts_explicit_token():
    client = Client(token="mn_test")
    assert client.token == "mn_test"


def test_client_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("FRESHJOTS_TOKEN", "mn_env")
    client = Client()
    assert client.token == "mn_env"


def test_api_error_carries_code_and_status():
    err = ApiError(status=422, code="cap_exceeded", message="over the limit")
    assert err.status == 422
    assert err.code == "cap_exceeded"
    assert str(err) == "over the limit"
