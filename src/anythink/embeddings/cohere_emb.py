"""Cohere embedding backend."""

from __future__ import annotations

import os

from anythink.embeddings.base import BaseEmbeddingBackend

_DEFAULT_MODEL = "embed-english-v3.0"
_API_URL = "https://api.cohere.com/v1/embed"

SUPPORTED_MODELS: dict[str, int] = {
    "embed-english-v3.0": 1024,
    "embed-multilingual-v3.0": 1024,
    "embed-english-light-v3.0": 384,
}


def _get_api_key() -> str | None:
    try:
        import keyring

        key = keyring.get_password("anythink", "cohere")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("COHERE_API_KEY")


class CohereEmbeddingBackend(BaseEmbeddingBackend):
    """Cohere embed API — uses httpx (no cohere SDK required)."""

    display_name = "Cohere Embeddings"

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name

    @property
    def name(self) -> str:  # type: ignore[override]
        if self._model_name == _DEFAULT_MODEL:
            return "cohere-emb"
        return f"cohere-emb/{self._model_name}"

    def is_available(self) -> bool:
        return _get_api_key() is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = _get_api_key()
        if not api_key:
            raise EnvironmentError(
                "Cohere API key not configured. Run: anythink keys add cohere"
            )
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model_name,
                    "texts": texts,
                    "input_type": "search_document",
                },
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]

    @property
    def dimensions(self) -> int:
        return SUPPORTED_MODELS.get(self._model_name, 1024)
