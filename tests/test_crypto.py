import pytest

from freshjots import Client, encrypt, decrypt, is_encrypted

# A fixed known-answer vector, embedded verbatim in the JS, Python, and Ruby
# test suites. All three decrypting this same token to the same plaintext is
# the cross-client interoperability guarantee for the fj1 format.
KAT_PASSPHRASE = "test-passphrase-123"
KAT_PLAINTEXT = "Fresh Jots ✔ interop\nline two"
KAT_TOKEN = (
    "fj1:n0zMBI1YWjNr84OlkYe1UZ6NQlez9Bre77p2CJe/BgmsOPFghVmAhriP+JEw0WXn7znpaiJHZrH42EgoZSTcp9pgDySf5dciijwvUVdUouwSC6ZyDpbIelOnvE+WFiUO"
)

# The encrypt/decrypt round-trips need the optional cryptography extra; the
# client_encrypted wiring tests below do not, so guard only the crypto ones.
try:
    import cryptography  # noqa: F401

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

requires_crypto = pytest.mark.skipif(not _HAS_CRYPTO, reason="needs freshjots[encryption]")


@requires_crypto
def test_round_trips_arbitrary_utf8():
    for msg in ["", "hello", "línea ñ 日本語 \U0001f510", "a\nb\nc"]:
        token = encrypt(msg, "pw")
        assert is_encrypted(token)
        assert decrypt(token, "pw") == msg


@requires_crypto
def test_output_is_single_line_with_prefix():
    token = encrypt("multi\nline\nplaintext", "pw")
    assert token.startswith("fj1:")
    assert "\n" not in token


@requires_crypto
def test_decrypts_shared_cross_client_vector():
    assert decrypt(KAT_TOKEN, KAT_PASSPHRASE) == KAT_PLAINTEXT


@requires_crypto
def test_wrong_passphrase_raises():
    token = encrypt("secret", "right")
    with pytest.raises(ValueError):
        decrypt(token, "wrong")


@requires_crypto
def test_tampered_ciphertext_raises():
    token = encrypt("secret", "pw")
    i = 8  # inside the base64 body (corrupts the salt -> key mismatch)
    swap = "B" if token[i] == "A" else "A"
    with pytest.raises(ValueError):
        decrypt(token[:i] + swap + token[i + 1:], "pw")


@requires_crypto
def test_randomized_output():
    assert encrypt("x", "pw") != encrypt("x", "pw")


def test_is_encrypted_and_decrypt_reject_plaintext():
    assert not is_encrypted("plain text")
    with pytest.raises(ValueError):
        decrypt("plain text", "pw")


def test_encrypt_without_cryptography_gives_helpful_error(monkeypatch):
    # Simulate the extra not being installed: block the import and confirm the
    # error names the extra to install.
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match=r"freshjots\[encryption\]"):
        encrypt("x", "pw")


def test_create_sends_client_encrypted(monkeypatch):
    client = Client(token="t")
    captured = {}

    def fake(method, path, body=None):
        captured["body"] = body
        return {"filename": "creds.txt"}

    monkeypatch.setattr(client, "_request", fake)
    client.create(title="creds", body="fj1:abc", client_encrypted=True)
    assert captured["body"]["note"]["client_encrypted"] is True


def test_create_omits_client_encrypted_by_default(monkeypatch):
    client = Client(token="t")
    captured = {}

    def fake(method, path, body=None):
        captured["body"] = body
        return {"filename": "x.txt"}

    monkeypatch.setattr(client, "_request", fake)
    client.create(title="x", body="y")
    assert "client_encrypted" not in captured["body"]["note"]


def test_append_sends_client_encrypted(monkeypatch):
    client = Client(token="t")
    captured = {}

    def fake(method, path, body=None):
        captured["body"] = body
        return {}

    monkeypatch.setattr(client, "_request", fake)
    client.append("log.txt", "fj1:abc", client_encrypted=True)
    assert captured["body"]["client_encrypted"] is True
