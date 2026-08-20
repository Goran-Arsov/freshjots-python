# freshjots — Python

Tiny Python client for the [Fresh Jots](https://freshjots.com) API. One
file, no runtime dependencies for the core client (uses `urllib` from
stdlib). Client-side [encryption](#encryption) is an optional extra.

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
- **Writing:** `create(title, body=, client_encrypted=)`, `append(filename, text, client_encrypted=)`, `update(id, **fields)`, `set(filename, **fields)`, `bulk(notes)`
- **Organizing:** `move(id_or_filename, folder=)`, `delete(id_or_filename)`, `folders()`, `folder(id)`, `create_folder(name)`, `rename_folder(id, name)`, `delete_folder(id)`

`note`/`note_by_id`/`create`/`update`/`set` return the note dict directly (no `{"note": …}` wrapper); `notes()` and `folders()` return lists. `update`/`set` accept any of `title`, `body`, `folder`, `root=True`, `deadline`, `alert_email`, `webhook_url`, `webhook_secret` — and because a content change rewrites the body as a unit, a `title` change must also pass `body`. `move`/`delete` accept a numeric id or a filename; `move`'s `folder` may be an id, a folder name, or `None`/`"none"`/`"root"` for the root.

## Encryption

Keep notes the server can't read: encrypt locally with your own passphrase,
store the ciphertext, decrypt locally on read. AES isn't in the standard
library, so this needs the optional extra:

```sh
pip install freshjots[encryption]
```

```python
import os
from freshjots import Client, encrypt, decrypt

client = Client()
pw = os.environ["FRESHJOTS_PASSPHRASE"]

# Store an encrypted note: encrypt the body, flag it client_encrypted.
client.create(title="Recovery codes", body=encrypt("1234-5678", pw), client_encrypted=True)

# Read it back and decrypt locally.
print(decrypt(client.note("recovery-codes")["plain_body"], pw))
```

The format (`fj1`: AES-256-CBC + HMAC-SHA256, PBKDF2-HMAC-SHA256) is
interoperable with the JS, Ruby, MCP, and shell (`brew`) clients. You hold the only key — Fresh Jots never receives it and
**cannot recover the note if you lose it**, so back the passphrase up somewhere
safe. Encryption is per-note and personal-only (not team notes); the title and
metadata stay in the clear, so keep secrets out of the title. `decrypt` raises
`ValueError` on a wrong passphrase. See <https://freshjots.com/encrypted-notes>.

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

Mint a token at <https://freshjots.com/settings/api_tokens> (Dev or
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
