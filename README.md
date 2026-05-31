# freshjots — Python

Tiny Python client for the [Fresh Jots](https://freshjots.com) API. One
file, no runtime dependencies (uses `urllib` from stdlib).

## Install

```sh
pip install freshjots
```

## Use

```python
from freshjots import Client

# Reads FRESHJOTS_TOKEN from the environment by default.
client = Client()

# Append text to a note (creates it if missing).
client.append("cron-jobs-prod", "backup ok")

# Read a note's body (by filename or numeric id).
print(client.note("cron-jobs-prod")["plain_body"])
print(client.note_by_id(42)["plain_body"])

# List notes — filter and paginate, or walk every page.
for note in client.notes(sort="created", folder_id=3, limit=20):
    print(f"{note['filename']}\t{note['title']}")
everything = client.notes(all_pages=True)

# Create by title (server derives the filename); or create many at once.
created = client.create(title="Research 2026 Q2", body="Initial outline.")
print(created["filename"])  # server-derived stream name
client.bulk([
    {"title": "Q2 plan", "plain_body": "…", "format": "plain"},
    {"title": "Q2 risks", "plain_body": "…", "format": "plain"},
])

# Edit a note by id or by filename (only the fields you pass change).
client.update(42, title="Renamed", body="rewritten")
client.set("cron-jobs-prod", alert_email="ops@example.com")

# Organize: move (by id or folder name), delete, manage folders.
client.move("cron-jobs-prod", folder="Ops")   # or folder=None for the root
client.delete("old-note")
client.create_folder("Archive")
for f in client.folders():
    print(f"{f['id']}\t{f['name']}")
```

The method surface mirrors the bash CLI:

- **Reading:** `notes(sort=, folder_id=, limit=, offset=, all_pages=)`, `note(filename)`, `note_by_id(id)`
- **Writing:** `create(title, body=)`, `append(filename, text)`, `update(id, **fields)`, `set(filename, **fields)`, `bulk(notes)`
- **Organizing:** `move(id_or_filename, folder=)`, `delete(id_or_filename)`, `folders()`, `folder(id)`, `create_folder(name)`, `rename_folder(id, name)`, `delete_folder(id)`

`note`/`note_by_id`/`create`/`update`/`set` return the note dict directly (no `{"note": …}` wrapper); `notes()` and `folders()` return lists. `update`/`set` accept any of `title`, `body`, `folder`, `root=True`, `deadline`, `alert_email`, `webhook_url`, `webhook_secret` — and because a content change rewrites the body as a unit, a `title` change must also pass `body`. `move`/`delete` accept a numeric id or a filename; `move`'s `folder` may be an id, a folder name, or `None`/`"none"`/`"root"` for the root.

## Errors

Any non-2xx response raises `freshjots.ApiError` with `status`, `code`,
`message`, and (when present) `details`:

```python
from freshjots import ApiError

try:
    client.append("huge", "x" * 5_000_000)
except ApiError as e:
    print(f"{e.status} {e.code}: {e}")
    # 413 content_too_large: body exceeds the per-note 3 MB cap
```

Stable error codes: `unauthenticated`, `forbidden`, `not_found`,
`validation_failed`, `cap_exceeded`, `storage_cap_exceeded`,
`content_too_large`, `content_type_mismatch`, `rate_limited`. Full list:
<https://freshjots.com/docs>.

## Auth

Mint a token at <https://freshjots.com/settings/api_tokens> (Pro or
Team tier required). Set it once, persisted for every new shell
(macOS defaults to zsh; use `~/.bashrc` on bash):

```sh
echo 'export FRESHJOTS_TOKEN=<your-token>' >> ~/.zshrc && source ~/.zshrc
```

Or pass explicitly:

```python
Client(token="mn_…")
```

## License

MIT.
