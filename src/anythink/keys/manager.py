"""API key management via the OS keychain."""

from __future__ import annotations

from typing import Any

import keyring
import keyring.errors
import yaml

from anythink.config.manager import Paths
from anythink.exceptions import KeychainError

_SERVICE = "anythink"


class KeyManager:
    """Stores and retrieves API keys via the OS keychain.

    A YAML index file tracks which providers have been configured because
    keyring has no list-by-service API.
    """

    def __init__(self, paths: Paths) -> None:
        self._paths = paths

    def set_key(self, provider: str, api_key: str) -> None:
        """Store an API key in the keychain and record the provider in the index."""
        try:
            keyring.set_password(_SERVICE, provider, api_key)
        except Exception as exc:
            raise KeychainError(
                f"Failed to store key for '{provider}': {exc}",
                user_message=f"Could not save the API key for '{provider}' to the keychain.",
            ) from exc
        self._add_to_index(provider)

    def get_key(self, provider: str) -> str | None:
        """Retrieve an API key from the keychain. Returns None if not set."""
        try:
            return keyring.get_password(_SERVICE, provider)
        except Exception as exc:
            raise KeychainError(
                f"Failed to retrieve key for '{provider}': {exc}",
                user_message=f"Could not read the API key for '{provider}' from the keychain.",
            ) from exc

    def delete_key(self, provider: str) -> None:
        """Remove an API key from the keychain and update the provider index."""
        try:
            keyring.delete_password(_SERVICE, provider)
        except keyring.errors.PasswordDeleteError:
            pass  # already absent — that's fine
        except Exception as exc:
            raise KeychainError(
                f"Failed to delete key for '{provider}': {exc}",
                user_message=f"Could not delete the API key for '{provider}'.",
            ) from exc
        self._remove_from_index(provider)

    def has_key(self, provider: str) -> bool:
        """Return True if an API key is stored for *provider*."""
        return self.get_key(provider) is not None

    def list_providers(self) -> list[str]:
        """Return sorted list of providers that have keys configured."""
        return sorted(self._load_index())

    # ── index helpers ──────────────────────────────────────────────────────────

    def _load_index(self) -> list[str]:
        index_file = self._paths.keyring_index_file
        if not index_file.exists():
            return []
        try:
            data: Any = yaml.safe_load(index_file.read_text()) or []
            return list(data) if isinstance(data, list) else []
        except yaml.YAMLError:
            return []

    def _save_index(self, providers: list[str]) -> None:
        self._paths.config_dir.mkdir(parents=True, exist_ok=True)
        self._paths.keyring_index_file.write_text(
            yaml.dump(sorted(providers), default_flow_style=False)
        )

    def _add_to_index(self, provider: str) -> None:
        providers = self._load_index()
        if provider not in providers:
            providers.append(provider)
            self._save_index(providers)

    def _remove_from_index(self, provider: str) -> None:
        providers = self._load_index()
        if provider in providers:
            providers.remove(provider)
            self._save_index(providers)
