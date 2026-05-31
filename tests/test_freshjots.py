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


def route(client, monkeypatch, by_path, default=None):
    """Like stub(), but returns a different payload per path (first key
    that is a substring of the request path wins). For methods that make
    more than one request (filename/folder-name resolution)."""
    calls = []

    def fake(self, method, path, body=None):
        calls.append((method, path, body))
        for key, val in by_path.items():
            if key in path:
                return val
        return {} if default is None else default

    monkeypatch.setattr(Client, "_request", fake)
    return calls


def test_version_is_pinned_to_1_1_0():
    assert __version__ == "1.1.0"


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


# ---- reading -----------------------------------------------------------


def test_note_returns_top_level_body(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 7, "filename": "cron jobs", "plain_body": "hello"})
    note = c.note("cron jobs")
    assert note["id"] == 7
    assert note["plain_body"] == "hello"  # would KeyError with the old ["note"]
    method, path, _ = calls[0]
    assert method == "GET"
    assert path == "/notes/by-filename/cron%20jobs"  # filename URL-encoded


def test_note_by_id_gets_top_level(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 7, "plain_body": "b"})
    note = c.note_by_id(7)
    assert note["id"] == 7
    assert calls[0] == ("GET", "/notes/7", None)


def test_notes_unwraps_the_notes_list(monkeypatch):
    c = Client(token="mn_x")
    stub(c, monkeypatch, {"notes": [{"id": 1}, {"id": 2}]})
    notes = c.notes()
    assert [n["id"] for n in notes] == [1, 2]


def test_notes_builds_filter_query(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"notes": []})
    c.notes(sort="created", folder_id=3, limit=20, offset=40)
    method, path, _ = calls[0]
    assert method == "GET"
    assert path.startswith("/notes?")
    for part in ("sort=created", "folder_id=3", "limit=20", "offset=40"):
        assert part in path


def test_notes_folder_none_filters_unfoldered(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"notes": []})
    c.notes(folder_id="none")
    assert "folder_id=none" in calls[0][1]


def test_notes_all_pages_walks_until_short_page(monkeypatch):
    c = Client(token="mn_x")
    pages = [{"notes": [{"id": i} for i in range(200)]}, {"notes": [{"id": 999}]}]
    calls = []

    def fake(self, method, path, body=None):
        calls.append((method, path, body))
        return pages[len(calls) - 1] if len(calls) <= len(pages) else {"notes": []}

    monkeypatch.setattr(Client, "_request", fake)
    result = c.notes(all_pages=True)
    assert len(result) == 201
    assert len(calls) == 2  # stopped on the short second page
    assert "limit=200" in calls[0][1] and "offset=0" in calls[0][1]
    assert "offset=200" in calls[1][1]


def test_notes_all_pages_resolves_folder_name_once(monkeypatch):
    c = Client(token="mn_x")
    pages = [{"notes": [{"id": i} for i in range(200)]}, {"notes": [{"id": 9}]}]
    folder_calls = {"n": 0}
    note_page = {"n": 0}

    def fake(self, method, path, body=None):
        if path == "/folders":
            folder_calls["n"] += 1
            return {"folders": [{"id": 7, "name": "Work"}]}
        page = pages[note_page["n"]] if note_page["n"] < len(pages) else {"notes": []}
        note_page["n"] += 1
        return page

    monkeypatch.setattr(Client, "_request", fake)
    result = c.notes(folder_id="Work", all_pages=True)
    assert len(result) == 201
    assert folder_calls["n"] == 1  # name resolved once, not once per page


# ---- writing -----------------------------------------------------------


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


def test_update_maps_fields_and_patches_by_id(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 5, "filename": "f"})
    c.update(5, title="New", body="rewritten", deadline=24, alert_email="a@b.com")
    method, path, body = calls[0]
    assert (method, path) == ("PATCH", "/notes/5")
    note = body["note"]
    assert note["title"] == "New"
    assert note["plain_body"] == "rewritten"  # body -> plain_body
    assert note["append_deadline_hours"] == 24  # deadline -> append_deadline_hours
    assert note["alert_email"] == "a@b.com"
    assert "format" not in note and "append_only" not in note  # not updatable


def test_update_title_only_is_refused():
    with pytest.raises(ValueError, match="rewrites the body"):
        Client(token="mn_x").update(5, title="New")


def test_update_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown update field"):
        Client(token="mn_x").update(5, body="x", bogus=1)


def test_update_root_sets_folder_null(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 5})
    c.update(5, root=True)
    assert calls[0][2]["note"]["folder_id"] is None


def test_set_patches_by_filename(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"filename": "deploys"})
    c.set("deploys", body="rewritten")
    method, path, body = calls[0]
    assert (method, path) == ("PATCH", "/notes/by-filename/deploys")
    assert body["note"]["plain_body"] == "rewritten"


def test_bulk_posts_notes_envelope(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"created": [{"id": 1}, {"id": 2}]})
    out = c.bulk([
        {"title": "a", "plain_body": "x", "format": "plain"},
        {"title": "b", "plain_body": "y", "format": "plain"},
    ])
    assert [n["id"] for n in out["created"]] == [1, 2]
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/notes/bulk")
    assert len(body["notes"]) == 2


def test_bulk_rejects_over_50():
    with pytest.raises(ValueError, match="at most 50"):
        Client(token="mn_x").bulk([{"title": str(i)} for i in range(51)])


def test_bulk_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        Client(token="mn_x").bulk([])


# ---- organizing --------------------------------------------------------


def test_delete_by_id(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {})
    assert c.delete(42) is True
    assert calls[0] == ("DELETE", "/notes/42", None)


def test_delete_resolves_filename_then_deletes(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 42})
    assert c.delete("my-note") is True
    assert calls[0] == ("GET", "/notes/by-filename/my-note", None)
    assert calls[1] == ("DELETE", "/notes/42", None)


def test_move_by_id_into_folder(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 42, "folder_id": 3})
    c.move(42, folder=3)
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/notes/42/move")
    assert body == {"folder_id": 3}


def test_move_to_root_sends_null(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 42, "folder_id": None})
    c.move(42, folder=None)
    assert calls[0][2] == {"folder_id": None}


def test_move_resolves_folder_name(monkeypatch):
    c = Client(token="mn_x")
    calls = route(c, monkeypatch, {"/folders": {"folders": [{"id": 3, "name": "Work"}]}},
                  default={"id": 42, "folder_id": 3})
    c.move(42, folder="Work")
    assert ("GET", "/folders", None) in calls  # consulted /folders to resolve the name
    method, path, body = calls[-1]
    assert (method, path) == ("POST", "/notes/42/move")
    assert body == {"folder_id": 3}


def test_move_unknown_folder_name_raises(monkeypatch):
    c = Client(token="mn_x")
    route(c, monkeypatch, {"/folders": {"folders": []}})
    with pytest.raises(ValueError, match="no folder named"):
        c.move(42, folder="Nope")


def test_folders_unwraps(monkeypatch):
    c = Client(token="mn_x")
    stub(c, monkeypatch, {"folders": [{"id": 1, "name": "Ops"}]})
    assert c.folders()[0]["name"] == "Ops"


def test_folder_gets_one(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 3, "name": "Work"})
    assert c.folder(3)["name"] == "Work"
    assert calls[0] == ("GET", "/folders/3", None)


def test_create_folder_posts_envelope(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 4, "name": "Archive"})
    c.create_folder("Archive")
    assert calls[0] == ("POST", "/folders", {"folder": {"name": "Archive"}})


def test_rename_folder_patches(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {"id": 4, "name": "Archive"})
    c.rename_folder(4, "Archive")
    assert calls[0] == ("PATCH", "/folders/4", {"folder": {"name": "Archive"}})


def test_delete_folder(monkeypatch):
    c = Client(token="mn_x")
    calls = stub(c, monkeypatch, {})
    assert c.delete_folder(4) is True
    assert calls[0] == ("DELETE", "/folders/4", None)
