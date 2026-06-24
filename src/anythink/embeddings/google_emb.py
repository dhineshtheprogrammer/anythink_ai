"""Google Generative AI embedding backend."""

from __future__ import annotations

import os

from anythink.embeddings.base import BaseEmbeddingBackend

_DEFAULT_MODEL = "text-embedding-004"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

SUPPORTED_MODELS: dict[str, int] = {
    "text-embedding-004": 768,
    "embedding-001": 768,
}


def _get_api_key() -> str | None:
    try:
        import keyring

        key = keyring.get_password("anythink", "gemini")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GOOGLE_API_KEY")


class GoogleEmbeddingBackend(BaseEmbeddingBackend):
    """Google Generative AI embedding API — uses httpx (no google SDK required)."""

    display_name = "Google Embeddings"

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name

    @property
    def name(self) -> str:  # type: ignore[override]
        if self._model_name == _DEFAULT_MODEL:
            return "google-emb"
        return f"google-emb/{self._model_name}"

    def is_available(self) -> bool:
        return _get_api_key() is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = _get_api_key()
        if not api_key:
            raise EnvironmentError(
                "Google API key not configured. Run: anythink keys add gemini"
            )
        import httpx

        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                url = f"{_API_BASE}/{self._model_name}:embedContent"
                resp = await client.post(
                    url,
                    params={"key": api_key},
                    json={
                        "model": f"models/{self._model_name}",
                        "content": {"parts": [{"text": text}]},
                    },
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"]["values"])
        return vectors

    @property
    def dimensions(self) -> int:
        return SUPPORTED_MODELS.get(self._model_name, 768)
