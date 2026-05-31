"""Tiny client for the Fresh Jots API (https://freshjots.com/docs).

Usage:

    from freshjots import Client

    client = Client()  # reads FRESHJOTS_TOKEN from the environment
    client.append("cron-jobs-prod", "backup ok")
    print(client.note("cron-jobs-prod")["plain_body"])
    created = client.create(title="Deploy log")
    print(created["filename"])  # server-derived from the title

The client mirrors the bash CLI's surface — reading (notes, note, note_by_id),
writing (create, append, update, set, bulk), and organizing (move, delete,
folders, folder, create_folder, rename_folder, delete_folder).

All methods raise freshjots.ApiError on non-2xx, with the code/status/details
from the API's stable error envelope.

Response shapes: GET /notes and GET /folders wrap their payloads
({"notes": [...]} / {"folders": [...]}). Every other note/folder endpoint
returns the object at the TOP LEVEL — there is no {"note": ...} wrapper.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.1.0"
DEFAULT_BASE_URL = "https://freshjots.com/api/v1"

__all__ = ["Client", "ApiError", "__version__"]

# Fields update()/set() may change (mirrors the bash CLI). append_only and
# format are intentionally excluded — the API does not allow updating them.
_UPDATABLE = (
    "title",
    "body",
    "folder",
    "root",
    "deadline",
    "alert_email",
    "webhook_url",
    "webhook_secret",
)

# The API caps a list page, and a bulk create batch, at these sizes.
_PAGE = 200
_BULK_MAX = 50
_ALL_PAGES_CAP = 100_000


class ApiError(Exception):
    def __init__(self, *, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


class Client:
    def __init__(self, token=None, base_url=DEFAULT_BASE_URL):
        self.token = token or os.environ.get("FRESHJOTS_TOKEN")
        if not self.token:
            raise ValueError("FRESHJOTS_TOKEN missing — pass token= or set the env var")
        self.base_url = base_url

    # ---- reading -------------------------------------------------------

    def notes(self, sort=None, folder_id=None, limit=None, offset=None, all_pages=False):
        """List notes (summary projection).

        sort is created|updated|appended (default updated server-side).
        folder_id filters to one folder: pass a folder id, a folder name
        (resolved via /folders), or "none"/"root" for un-foldered notes
        only. limit/offset paginate (the server caps a page at 200).
        all_pages=True walks every page and returns the full list (limit
        and offset are then ignored).
        """
        if all_pages:
            # Resolve a folder name to its id ONCE, not once per page — the
            # resolved value (an id or "none") passes through unchanged below.
            folder = folder_id
            if folder_id is not None and str(folder_id) != "":
                folder = self._notes_folder_filter(folder_id)
            out = []
            page_offset = 0
            while True:
                page = self._list_notes(sort, folder, _PAGE, page_offset)
                out.extend(page)
                if len(page) < _PAGE or page_offset >= _ALL_PAGES_CAP:
                    break
                page_offset += _PAGE
            return out
        return self._list_notes(sort, folder_id, limit, offset)

    def note(self, filename):
        """Fetch one note by filename. Returns the full note dict."""
        return self._request("GET", f"/notes/by-filename/{self._escape(filename)}")

    def note_by_id(self, id):
        """Fetch one note by numeric id. Returns the full note dict."""
        return self._request("GET", f"/notes/{self._escape(id)}")

    # ---- writing -------------------------------------------------------

    def create(self, title, body=""):
        """Create a note by title (the server derives the filename). For a
        note addressable by an exact filename, use append() instead."""
        if not title:
            raise ValueError(
                "create requires a title — the API derives the filename from it. "
                "For a note addressable by an exact filename, use append()."
            )
        payload = {"note": {"title": title, "plain_body": body, "format": "plain"}}
        return self._request("POST", "/notes", payload)

    def append(self, filename, text):
        """Append text to a note. Creates the note if it doesn't exist yet."""
        path = f"/notes/by-filename/{self._escape(filename)}/append"
        self._request("POST", path, {"text": text})
        return True

    def update(self, id, **fields):
        """Update a note by id. Pass any of: title, body, folder, root=True,
        deadline, alert_email, webhook_url, webhook_secret — only the keys
        you pass are changed. A content change (title/body) rewrites the
        body as a unit, so a title change needs body too (the API requires
        plain_body). append_only and format are not updatable.
        """
        return self._request(
            "PATCH", f"/notes/{self._escape(id)}", {"note": self._note_fields(fields)}
        )

    def set(self, filename, **fields):
        """Update a note addressed by filename. Same fields as update()."""
        return self._request(
            "PATCH",
            f"/notes/by-filename/{self._escape(filename)}",
            {"note": self._note_fields(fields)},
        )

    def bulk(self, notes):
        """Create up to 50 notes atomically. `notes` is a list of note dicts
        ({"title": ..., "plain_body": ..., "format": "plain"}). Returns the
        response ({"created": [...]})."""
        items = list(notes)
        if not items:
            raise ValueError("bulk requires at least one note")
        if len(items) > _BULK_MAX:
            raise ValueError(f"bulk accepts at most {_BULK_MAX} notes (got {len(items)})")
        return self._request("POST", "/notes/bulk", {"notes": items})

    # ---- organizing ----------------------------------------------------

    def delete(self, id_or_filename):
        """Delete a note by id or filename. Locked (append-only) notes are
        refused by the API. Returns True."""
        self._request("DELETE", f"/notes/{self._resolve_note_id(id_or_filename)}")
        return True

    def move(self, id_or_filename, folder=None):
        """Move a note into a folder. `folder` may be a folder id, a folder
        name (resolved via /folders), or None/"none"/"root" for the root."""
        note_id = self._resolve_note_id(id_or_filename)
        return self._request(
            "POST", f"/notes/{note_id}/move", {"folder_id": self._resolve_folder_id(folder)}
        )

    def folders(self):
        """List your folders ({"folders": [...]} envelope)."""
        return self._request("GET", "/folders")["folders"]

    def folder(self, id):
        """Fetch one folder by id. Returns the folder dict."""
        return self._request("GET", f"/folders/{self._escape(id)}")

    def create_folder(self, name):
        """Create a folder. Returns the created folder dict."""
        return self._request("POST", "/folders", {"folder": {"name": name}})

    def rename_folder(self, id, name):
        """Rename a folder. Returns the updated folder dict."""
        return self._request(
            "PATCH", f"/folders/{self._escape(id)}", {"folder": {"name": name}}
        )

    def delete_folder(self, id):
        """Delete a folder by id. Returns True."""
        self._request("DELETE", f"/folders/{self._escape(id)}")
        return True

    # ---- internals -----------------------------------------------------

    def _list_notes(self, sort, folder_id, limit, offset):
        query = {}
        if sort:
            query["sort"] = sort
        if folder_id is not None and str(folder_id) != "":
            query["folder_id"] = self._notes_folder_filter(folder_id)
        if limit is not None:
            query["limit"] = limit
        if offset is not None:
            query["offset"] = offset
        path = "/notes?" + urllib.parse.urlencode(query) if query else "/notes"
        return self._request("GET", path)["notes"]

    def _notes_folder_filter(self, value):
        # For the list filter, "none"/"root" mean "un-foldered only" (the
        # literal the API expects); a numeric id passes through; a name is
        # resolved to its id.
        s = str(value)
        if s.lower() in ("none", "root", "null"):
            return "none"
        if s.isdigit():
            return s
        return self._resolve_folder_id(value)

    def _note_fields(self, fields):
        unknown = set(fields) - set(_UPDATABLE)
        if unknown:
            raise ValueError(
                f"unknown update field(s): {', '.join(sorted(unknown))}. "
                f"allowed: {', '.join(_UPDATABLE)} "
                "(append_only/format are not updatable)"
            )
        # A content change rewrites the body as a unit; the API requires
        # plain_body, so a title-only change is refused (mirrors the CLI).
        if "title" in fields and "body" not in fields:
            raise ValueError(
                "changing the title also rewrites the body — pass body= too. "
                "For metadata only, use folder/root/deadline/alert_email/webhook_* "
                "without title."
            )
        note = {}
        if "title" in fields:
            note["title"] = fields["title"]
        if "body" in fields:
            note["plain_body"] = fields["body"]
        if fields.get("root"):
            note["folder_id"] = None
        elif "folder" in fields:
            note["folder_id"] = self._resolve_folder_id(fields["folder"])
        if "deadline" in fields:
            note["append_deadline_hours"] = fields["deadline"]
        if "alert_email" in fields:
            note["alert_email"] = fields["alert_email"]
        if "webhook_url" in fields:
            note["webhook_url"] = fields["webhook_url"]
        if "webhook_secret" in fields:
            note["webhook_secret"] = fields["webhook_secret"]
        if not note:
            raise ValueError("no fields to update")
        return note

    def _resolve_note_id(self, value):
        # A numeric id is used as-is; a filename is resolved via the
        # by-filename lookup (which carries the note's id).
        if isinstance(value, int) or str(value).isdigit():
            return value
        return self.note(str(value))["id"]

    def _resolve_folder_id(self, value):
        # Resolves to a folder id (or None for the root). Names go through
        # /folders; an unknown or ambiguous name is a ValueError.
        if value is None or str(value).lower() in ("none", "root", "null"):
            return None
        if isinstance(value, int):
            return value
        if str(value).isdigit():
            return int(value)
        matches = [f for f in self.folders() if f.get("name") == str(value)]
        if not matches:
            raise ValueError(f"no folder named '{value}'")
        if len(matches) > 1:
            raise ValueError(f"ambiguous folder name '{value}' — use its id")
        return matches[0]["id"]

    def _escape(self, value):
        return urllib.parse.quote(str(value), safe="")

    def _request(self, method, path, body=None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}"}
        if data:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                payload = resp.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as e:
            error_payload = {}
            try:
                error_payload = json.loads(e.read() or b"{}")
            except (json.JSONDecodeError, ValueError):
                pass
            err = error_payload.get("error", {})
            raise ApiError(
                status=e.code,
                code=err.get("code", "unknown"),
                message=err.get("message", "request failed"),
                details=err.get("details"),
            ) from e
