"""Tests for keys/manager.py."""

from __future__ import annotations

from unittest.mock import patch

import keyring.errors
import pytest
import yaml

from anythink.config.manager import Paths
from anythink.exceptions import KeychainError
from anythink.keys.manager import KeyManager


@pytest.fixture()
def km(xdg_dirs: Paths) -> KeyManager:
    return KeyManager(paths=xdg_dirs)


# ── get / set / has ───────────────────────────────────────────────────────────


class TestGetSetHas:
    def test_get_returns_none_when_not_set(self, km: KeyManager) -> None:
        with patch("keyring.get_password", return_value=None):
            assert km.get_key("groq") is None

    def test_has_key_false_when_not_set(self, km: KeyManager) -> None:
        with patch("keyring.get_password", return_value=None):
            assert km.has_key("groq") is False

    def test_set_calls_keyring(self, km: KeyManager) -> None:
        with (
            patch("keyring.set_password") as mock_set,
            patch("keyring.get_password", return_value="sk-abc"),
        ):
            km.set_key("groq", "sk-abc")
            mock_set.assert_called_once_with("anythink", "groq", "sk-abc")

    def test_get_returns_stored_value(self, km: KeyManager) -> None:
        with patch("keyring.get_password", return_value="sk-xyz"):
            assert km.get_key("openai") == "sk-xyz"

    def test_has_key_true_after_set(self, km: KeyManager) -> None:
        with patch("keyring.set_password"), patch("keyring.get_password", return_value="val"):
            km.set_key("anthropic", "val")
            assert km.has_key("anthropic") is True

    def test_set_key_raises_keychainerror_on_failure(self, km: KeyManager) -> None:
        with patch("keyring.set_password", side_effect=RuntimeError("backend error")):
            with pytest.raises(KeychainError, match="store key"):
                km.set_key("groq", "sk-bad")

    def test_get_key_raises_keychainerror_on_failure(self, km: KeyManager) -> None:
        with patch("keyring.get_password", side_effect=RuntimeError("backend error")):
            with pytest.raises(KeychainError, match="retrieve key"):
                km.get_key("groq")


# ── delete ────────────────────────────────────────────────────────────────────


class TestDeleteKey:
    def test_delete_calls_keyring(self, km: KeyManager) -> None:
        with patch("keyring.delete_password") as mock_del:
            km.delete_key("groq")
            mock_del.assert_called_once_with("anythink", "groq")

    def test_delete_ignores_password_delete_error(self, km: KeyManager) -> None:
        with patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError):
            km.delete_key("groq")  # must not raise

    def test_delete_raises_keychainerror_on_unexpected_error(self, km: KeyManager) -> None:
        with patch("keyring.delete_password", side_effect=OSError("permission denied")):
            with pytest.raises(KeychainError, match="delete key"):
                km.delete_key("groq")


# ── index management ──────────────────────────────────────────────────────────


class TestIndex:
    def test_list_providers_empty_initially(self, km: KeyManager) -> None:
        assert km.list_providers() == []

    def test_set_adds_provider_to_index(self, km: KeyManager) -> None:
        with patch("keyring.set_password"):
            km.set_key("groq", "sk-1")
        assert "groq" in km.list_providers()

    def test_list_providers_sorted(self, km: KeyManager) -> None:
        with patch("keyring.set_password"):
            km.set_key("openai", "sk-o")
            km.set_key("anthropic", "sk-a")
        assert km.list_providers() == ["anthropic", "openai"]

    def test_duplicate_set_does_not_duplicate_in_index(self, km: KeyManager) -> None:
        with patch("keyring.set_password"):
            km.set_key("groq", "sk-1")
            km.set_key("groq", "sk-2")
        assert km.list_providers().count("groq") == 1

    def test_delete_removes_provider_from_index(self, km: KeyManager) -> None:
        with patch("keyring.set_password"):
            km.set_key("groq", "sk-1")
        with patch("keyring.delete_password"):
            km.delete_key("groq")
        assert "groq" not in km.list_providers()

    def test_delete_nonexistent_provider_no_error(self, km: KeyManager) -> None:
        with patch("keyring.delete_password"):
            km.delete_key("nonexistent")  # must not raise

    def test_index_file_written_after_set(self, km: KeyManager, xdg_dirs: Paths) -> None:
        with patch("keyring.set_password"):
            km.set_key("gemini", "k1")
        assert xdg_dirs.keyring_index_file.exists()
        raw = yaml.safe_load(xdg_dirs.keyring_index_file.read_text())
        assert "gemini" in raw

    def test_corrupt_index_returns_empty_list(self, km: KeyManager, xdg_dirs: Paths) -> None:
        xdg_dirs.keyring_index_file.write_text("!!bad_yaml")
        assert km.list_providers() == []

    def test_non_list_index_returns_empty_list(self, km: KeyManager, xdg_dirs: Paths) -> None:
        xdg_dirs.keyring_index_file.write_text("key: value\n")
        assert km.list_providers() == []
