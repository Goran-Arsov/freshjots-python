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

# Read a note's body.
print(client.note("cron-jobs-prod")["plain_body"])

# List your notes.
for note in client.notes():
    print(f"{note['filename']}\t{note['title']}")

# Create a new note explicitly (errors if the filename is taken).
client.create("research-2026-q2", body="Initial outline.")
```

The whole API is four methods: `notes()`, `note(filename)`,
`create(filename, body, title)`, `append(filename, text)`.

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
Dev-pro tier required). Set it once:

```sh
export FRESHJOTS_TOKEN=<your-token>
```

Or pass explicitly:

```python
Client(token="fjk_…")
```

## License

MIT.
