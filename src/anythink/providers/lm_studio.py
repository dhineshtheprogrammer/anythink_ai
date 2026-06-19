"""LM Studio local provider for Anythink (OpenAI-compatible API)."""

from __future__ import annotations

from anythink.providers.openai import OpenAIProvider

_DEFAULT_BASE_URL = "http://localhost:1234/v1"


class LMStudioProvider(OpenAIProvider):
    """LM Studio uses an OpenAI-compatible HTTP API at a local port.

    No API key is required.
    """

    name = "lm_studio"
    display_name = "LM Studio"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(api_key="lm-studio", base_url=base_url or _DEFAULT_BASE_URL)

    @property
    def requires_api_key(self) -> bool:
        return False

    @property
    def supports_vision(self) -> bool:
        return True  # depends on the loaded model, but many support it
