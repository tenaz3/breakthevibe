"""Unit tests for InMemoryChallengeStore."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from breakthevibe.web.auth.challenge_store import InMemoryChallengeStore


@pytest.mark.unit
class TestInMemoryChallengeStore:
    def test_set_and_pop(self) -> None:
        store = InMemoryChallengeStore()
        store.set("key1", b"challenge-bytes", ttl_seconds=60)
        result = store.pop("key1")
        assert result == b"challenge-bytes"

    def test_pop_removes_entry(self) -> None:
        store = InMemoryChallengeStore()
        store.set("key1", b"challenge-bytes")
        store.pop("key1")
        assert store.pop("key1") is None

    def test_pop_missing_key(self) -> None:
        store = InMemoryChallengeStore()
        assert store.pop("nonexistent") is None

    def test_expired_entry_returns_none(self) -> None:
        store = InMemoryChallengeStore()
        store.set("key1", b"challenge", ttl_seconds=1)

        with patch.object(time, "time", return_value=time.time() + 5):
            assert store.pop("key1") is None

    def test_cleanup_removes_expired(self) -> None:
        store = InMemoryChallengeStore()
        store.set("old", b"old-challenge", ttl_seconds=1)

        # Manually expire
        store._store["old"] = (b"old-challenge", time.time() - 10)

        store.set("new", b"new-challenge", ttl_seconds=60)
        assert "old" not in store._store
        assert store.pop("new") == b"new-challenge"

    def test_multiple_keys(self) -> None:
        store = InMemoryChallengeStore()
        store.set("a", b"challenge-a")
        store.set("b", b"challenge-b")
        assert store.pop("a") == b"challenge-a"
        assert store.pop("b") == b"challenge-b"

    def test_overwrite_key(self) -> None:
        store = InMemoryChallengeStore()
        store.set("key", b"first")
        store.set("key", b"second")
        assert store.pop("key") == b"second"
