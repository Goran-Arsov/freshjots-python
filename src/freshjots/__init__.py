"""Tiny client for the Fresh Jots API (https://freshjots.com/docs).

Usage:

    from freshjots import Client

    client = Client()  # reads FRESHJOTS_TOKEN from the environment
    client.append("cron-jobs-prod", "backup ok")
    print(client.note("cron-jobs-prod")["plain_body"])

All methods raise freshjots.ApiError on non-2xx, with the code/status/details
from the API's stable error envelope.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.1.0"
DEFAULT_BASE_URL = "https://freshjots.com/api/v1"

__all__ = ["Client", "ApiError", "__version__"]


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

    def notes(self):
        """List your notes (summary projection — filename, title, etc.)."""
        return self._request("GET", "/notes")["notes"]

    def note(self, filename):
        """Fetch one note by its filename. Returns the full note dict."""
        path = f"/notes/by-filename/{urllib.parse.quote(filename, safe='')}"
        return self._request("GET", path)["note"]

    def create(self, filename, body="", title=None):
        """Create a new note. Errors if `filename` is already in use."""
        payload = {"note": {"filename": filename, "plain_body": body, "format": "plain"}}
        if title:
            payload["note"]["title"] = title
        return self._request("POST", "/notes", payload)["note"]

    def append(self, filename, text):
        """Append text to a note. Creates the note if it doesn't exist yet."""
        path = f"/notes/by-filename/{urllib.parse.quote(filename, safe='')}/append"
        self._request("POST", path, {"text": text})
        return True

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
