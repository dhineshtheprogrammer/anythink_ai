"""Ollama embedding backend — local Ollama server, no API key required."""

from __future__ import annotations

from anythink.embeddings.base import BaseEmbeddingBackend

_DEFAULT_MODEL = "nomic-embed-text"
_DEFAULT_BASE_URL = "http://localhost:11434"

SUPPORTED_MODELS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
    "snowflake-arctic-embed": 1024,
}


class OllamaEmbeddingBackend(BaseEmbeddingBackend):
    """Embeddings via a local Ollama server — no API key, no extra deps."""

    display_name = "Ollama"

    def __init__(
        self, model_name: str = _DEFAULT_MODEL, base_url: str = _DEFAULT_BASE_URL
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:  # type: ignore[override]
        if self._model_name == _DEFAULT_MODEL:
            return "ollama"
        return f"ollama/{self._model_name}"

    def is_available(self) -> bool:
        try:
            import httpx

            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model_name, "prompt": text},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        return vectors

    @property
    def dimensions(self) -> int:
        return SUPPORTED_MODELS.get(self._model_name, 768)
