"""OpenAI embedding backend (text-embedding-3-small / large)."""

from __future__ import annotations

import os

from anythink.embeddings.base import BaseEmbeddingBackend

_DEFAULT_MODEL = "text-embedding-3-small"
_API_URL = "https://api.openai.com/v1/embeddings"

SUPPORTED_MODELS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


def _get_api_key() -> str | None:
    try:
        import keyring

        key = keyring.get_password("anythink", "openai")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


class OpenAIEmbeddingBackend(BaseEmbeddingBackend):
    """OpenAI text-embedding API — uses httpx (no openai SDK required)."""

    display_name = "OpenAI Embeddings"

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name

    @property
    def name(self) -> str:  # type: ignore[override]
        if self._model_name == _DEFAULT_MODEL:
            return "openai-emb"
        return f"openai-emb/{self._model_name}"

    def is_available(self) -> bool:
        return _get_api_key() is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = _get_api_key()
        if not api_key:
            raise EnvironmentError(
                "OpenAI API key not configured. Run: anythink keys add openai"
            )
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": self._model_name, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]

    @property
    def dimensions(self) -> int:
        return SUPPORTED_MODELS.get(self._model_name, 1536)
