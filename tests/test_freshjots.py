"""Tests — no network. Token/ApiError checks are pure; the method tests
stub the transport (Client._request) so they assert the real request
shape and response handling (these would have caught the top-level-
serializer and unpermitted-filename bugs)."""
import pytest

from freshjots import ApiError, Client, __version__


def stub(client, monkeypatch, return_value):
    """Replace Client._request with a recorder. Returns the calls list;
    each entry is (method, path, body)."""
    calls = []

    def fake(self, method, path, body=None):
        calls.append((method, path, body))
        return return_value

    monkeypatch.setattr(Client, "_request", fake)
    return calls


def test_version_is_pinned_to_0_2_0():
    assert __version__ == "0.2.0"


def test_client_requires_a_token(monkeypatch):
    monkeypatch.delenv("FRESHJOTS_TOKEN", raising=False)
    with pytest.raises(ValueError, match="FRESHJOTS_TOKEN"):
        Client()


def test_client_accepts_explicit_token():
    assert Client(token="mn_test").token == "mn_test"


def test_client_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("FRESHJOTS_TOKEN", "mn_env")
    assert Client().token == "mn_env"


def test_api_error_carries_code_and_status():
    err = ApiError(status=422, code="cap_exceeded", message="over the limit")
    assert err.status == 422
    assert err.code == "cap_exceeded"
    assert str(err) == "over the limit"


def test_note_returns_top_level_body(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 7, "filename": "cron jobs", "plain_body": "hello"})
    note = c.note("cron jobs")
    assert note["id"] == 7
    assert note["plain_body"] == "hello"  # would KeyError with the old ["note"]
    method, path, _ = calls[0]
    assert method == "GET"
    assert path == "/notes/by-filename/cron%20jobs"  # filename URL-encoded


def test_notes_unwraps_the_notes_list(monkeypatch):
    c = Client(token="mn_x")
    stub(c, monkeypatch, {"notes": [{"id": 1}, {"id": 2}]})
    notes = c.notes()
    assert [n["id"] for n in notes] == [1, 2]


def test_create_requires_a_title():
    with pytest.raises(ValueError, match="create requires a title"):
        Client(token="mn_x").create(title="")


def test_create_posts_title_never_filename(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 9, "filename": "research-2026-q2", "title": "Research 2026 Q2"})
    created = c.create(title="Research 2026 Q2", body="o")
    assert created["id"] == 9
    assert created["filename"] == "research-2026-q2"  # server-derived
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/notes")
    assert body["note"]["title"] == "Research 2026 Q2"
    assert body["note"]["format"] == "plain"
    assert "filename" not in body["note"]  # API does not permit it


def test_append_posts_text_to_by_filename(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 1, "created": False})
    assert c.append("deploys", "shipped") is True
    method, path, body = calls[0]
    assert method == "POST"
    assert path == "/notes/by-filename/deploys/append"
    assert body == {"text": "shipped"}
