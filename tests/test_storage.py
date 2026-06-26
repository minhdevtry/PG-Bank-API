"""Test the storage abstraction (BaseSessionStorage, FileSessionStorage, DirSessionStorage, MemorySessionStorage)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgbank_unofficial.storage import (
    BaseAsyncSessionStorage,
    BaseSessionStorage,
    DirSessionStorage,
    FileSessionStorage,
    MemorySessionStorage,
)

FAKE_MOUNT = {
    "serverPubKeyFallback": "fakekey" * 20,
    "tokenFallback": "default_token_value_" + "x" * 10,
}


# ── FileSessionStorage ────────────────────────────────────────────────────────


def test_file_session_storage_save_creates_parent(tmp_path: Path):
    """save_session should create the parent directory if missing."""
    target = tmp_path / "deep" / "nested" / "session.json"
    storage = FileSessionStorage(target)
    storage.save_session("alice", {"sessionId": "sess_1", "token": "tok_a"})
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["sessionId"] == "sess_1"
    assert data["token"] == "tok_a"


def test_file_session_storage_load_returns_none_if_missing(tmp_path: Path):
    """load_session should return None if file does not exist."""
    storage = FileSessionStorage(tmp_path / "nonexistent.json")
    assert storage.load_session("alice") is None


def test_file_session_storage_load_returns_none_for_invalid_json(tmp_path: Path):
    """load_session should return None if file content is malformed."""
    target = tmp_path / "session.json"
    target.write_text("not-valid-json", encoding="utf-8")
    storage = FileSessionStorage(target)
    assert storage.load_session("alice") is None


def test_file_session_storage_delete_removes_file(tmp_path: Path):
    """delete_session should remove the session file."""
    target = tmp_path / "session.json"
    target.write_text("{}", encoding="utf-8")
    storage = FileSessionStorage(target)
    storage.delete_session("alice")
    assert not target.exists()


def test_file_session_storage_delete_noop_for_missing(tmp_path: Path):
    """delete_session should not raise if file does not exist."""
    storage = FileSessionStorage(tmp_path / "missing.json")
    storage.delete_session("alice")  # should not raise


# ── DirSessionStorage ─────────────────────────────────────────────────────────


def test_dir_session_storage_creates_directory(tmp_path: Path):
    """Constructor should create the sessions directory if missing."""
    target_dir = tmp_path / "sessions"
    DirSessionStorage(target_dir)
    assert target_dir.exists()
    assert target_dir.is_dir()


def test_dir_session_storage_separate_files_per_username(tmp_path: Path):
    """Each username should get its own JSON file in the directory."""
    storage = DirSessionStorage(tmp_path / "sessions")
    storage.save_session("alice", {"sessionId": "sess_a", "token": "tok_a"})
    storage.save_session("bob", {"sessionId": "sess_b", "token": "tok_b"})

    files = list((tmp_path / "sessions").glob("*.json"))
    assert len(files) == 2

    alice_data = storage.load_session("alice")
    bob_data = storage.load_session("bob")
    assert alice_data["sessionId"] == "sess_a"
    assert bob_data["sessionId"] == "sess_b"
    assert alice_data["token"] == "tok_a"
    assert bob_data["token"] == "tok_b"


def test_dir_session_storage_load_returns_none_for_missing(tmp_path: Path):
    """load_session should return None if file does not exist for username."""
    storage = DirSessionStorage(tmp_path / "sessions")
    assert storage.load_session("nobody") is None


def test_dir_session_storage_sanitizes_filename(tmp_path: Path):
    """Filenames should be sanitized to avoid path traversal escapes."""
    storage = DirSessionStorage(tmp_path / "sessions")
    storage.save_session("../../etc/passwd", {"sessionId": "sess_x"})
    # The file should be saved INSIDE sessions_dir, not outside it
    assert (tmp_path / "sessions" / "etcpasswd.json").exists()
    # And the malicious path resolution should not exist
    assert not (tmp_path.parent / "etc" / "passwd.json").exists()


def test_dir_session_storage_delete_removes_file(tmp_path: Path):
    """delete_session should remove only the matching file."""
    storage = DirSessionStorage(tmp_path / "sessions")
    storage.save_session("alice", {"sessionId": "sess_a"})
    storage.save_session("bob", {"sessionId": "sess_b"})
    storage.delete_session("alice")
    assert storage.load_session("alice") is None
    assert storage.load_session("bob") is not None


# ── MemorySessionStorage ──────────────────────────────────────────────────────


def test_memory_session_storage_save_and_load():
    """In-memory storage should save and load the same data."""
    storage = MemorySessionStorage()
    storage.save_session("alice", {"sessionId": "sess_a", "token": "tok_a"})
    loaded = storage.load_session("alice")
    assert loaded is not None
    assert loaded["sessionId"] == "sess_a"


def test_memory_session_storage_load_returns_none_for_missing():
    """load_session should return None for unknown username."""
    storage = MemorySessionStorage()
    assert storage.load_session("ghost") is None


def test_memory_session_storage_copies_on_save():
    """save_session should copy data so external mutations don't affect storage."""
    storage = MemorySessionStorage()
    payload = {"sessionId": "sess_a"}
    storage.save_session("alice", payload)
    payload["sessionId"] = "mutated"
    assert storage.load_session("alice")["sessionId"] == "sess_a"


def test_memory_session_storage_delete():
    """delete_session should remove the entry."""
    storage = MemorySessionStorage()
    storage.save_session("alice", {"sessionId": "sess_a"})
    storage.delete_session("alice")
    assert storage.load_session("alice") is None


def test_memory_session_storage_delete_unknown_noop():
    """delete_session on unknown username should not raise."""
    storage = MemorySessionStorage()
    storage.delete_session("ghost")  # no-op


# ── ABC inheritance / interface contracts ─────────────────────────────────────


def test_file_storage_is_base_session_storage(tmp_path: Path):
    """FileSessionStorage should be a subclass of BaseSessionStorage."""
    assert issubclass(FileSessionStorage, BaseSessionStorage)


def test_dir_storage_is_base_session_storage(tmp_path: Path):
    """DirSessionStorage should be a subclass of BaseSessionStorage."""
    assert issubclass(DirSessionStorage, BaseSessionStorage)


def test_memory_storage_is_base_session_storage():
    """MemorySessionStorage should be a subclass of BaseSessionStorage."""
    assert issubclass(MemorySessionStorage, BaseSessionStorage)


def test_custom_storage_backend_via_subclass():
    """User-defined backends should integrate via subclassing BaseSessionStorage."""

    class InMemoryBackend(BaseSessionStorage):
        def __init__(self):
            self._store = {}

        def save_session(self, username, data):
            self._store[username] = data

        def load_session(self, username):
            return self._store.get(username)

        def delete_session(self, username):
            self._store.pop(username, None)

    backend = InMemoryBackend()
    backend.save_session("u1", {"sessionId": "s1"})
    assert backend.load_session("u1")["sessionId"] == "s1"
    backend.delete_session("u1")
    assert backend.load_session("u1") is None


# ── Custom backend integration with PGBankClient ──────────────────────────────


def test_pgbank_client_uses_custom_storage_backend():
    """PGBankClient should use a custom storage backend for save/load."""
    saved_entries = {}

    class CapturingStorage(BaseSessionStorage):
        def save_session(self, username, data):
            saved_entries["saved"] = (username, data)

        def load_session(self, username):
            return None

        def delete_session(self, username):
            saved_entries["deleted"] = username

    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        from pgbank_unofficial import PGBankClient

        client = PGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_storage=CapturingStorage(),
            auto_login=False,
        )
        client.session_id = "sess_999"
        client._save_session()
        assert "saved" in saved_entries
        username, data = saved_entries["saved"]
        assert username == "alice"
        assert data["sessionId"] == "sess_999"
        client.logout()
        assert saved_entries.get("deleted") == "alice"


def test_pgbank_client_session_path_falls_back_to_file_storage(tmp_path: Path):
    """PGBankClient with session_path should internally use FileSessionStorage."""
    session_file = tmp_path / "session.json"
    with patch("pgbank_unofficial.client.fetch_mount_config", return_value=FAKE_MOUNT):
        from pgbank_unofficial import PGBankClient

        client = PGBankClient(
            username="alice",
            password="secret",
            browser_id="bid_xxx",
            session_path=session_file,
            auto_login=False,
        )
        # The internal storage should be a FileSessionStorage wrapping session_file
        from pgbank_unofficial.storage import FileSessionStorage
        assert isinstance(client._session_storage, FileSessionStorage)
        assert client._session_storage.session_path == session_file
