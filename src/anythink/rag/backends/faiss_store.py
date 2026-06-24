"""FAISS vector store backend — flat exact-nearest-neighbour search.

Requires ``pip install anythink[rag-faiss]`` (faiss-cpu>=1.8).

Storage layout (base_path = {cache_dir}/{safe_name}):
  {base_path}.faiss   — FAISS IndexFlatIP serialised with faiss.write_index
  {base_path}.meta.gz — gzip-JSON list of {text, metadata} dicts (same order)

Inner-product index (IndexFlatIP) with L2-normalised vectors gives exact
cosine-similarity search in O(n·d).  For indexes > 1 M chunks, consider
switching to IndexIVFFlat (approximate, but much faster).

``get_vector_at(idx)`` uses ``faiss.index.reconstruct(idx)`` — supported for
flat (exact) indexes.  The cost is O(1) for IndexFlatIP.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

from anythink.exceptions import RAGError
from anythink.rag.backends.base import BaseVectorStore

_FAISS_SUFFIX = ".faiss"
_META_SUFFIX = ".meta.gz"


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0.0:
        return v
    return [x / norm for x in v]


class FAISSVectorStore(BaseVectorStore):
    """FAISS IndexFlatIP backend with cosine-similarity queries."""

    def __init__(self) -> None:
        self._index: object | None = None  # faiss.IndexFlatIP, loaded lazily
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []
        self._dim: int = 0

    def is_available(self) -> bool:
        """True if faiss-cpu is installed."""
        try:
            import faiss  # noqa: F401

            return True
        except ImportError:
            return False

    def _require_faiss(self) -> Any:
        try:
            import faiss

            return faiss
        except ImportError as exc:
            raise RAGError(
                "faiss-cpu not installed.",
                user_message="FAISS backend requires: pip install anythink[rag-faiss]",
            ) from exc

    def _init_index(self, dim: int) -> None:
        faiss = self._require_faiss()
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if not vectors:
            return

        import numpy as np

        faiss = self._require_faiss()
        dim = len(vectors[0])
        if self._index is None:
            self._init_index(dim)

        normed = [_normalize(v) for v in vectors]
        arr = np.array(normed, dtype="float32")
        self._index.add(arr)  # type: ignore[union-attr]
        self._texts.extend(texts)
        self._metas.extend(metadatas)

    def remove_by_source(self, source_path: str) -> int:
        keep = [
            i
            for i, m in enumerate(self._metas)
            if str(m.get("source_path", "")) != source_path
        ]
        removed = len(self._metas) - len(keep)
        if removed == 0:
            return 0

        old_texts = self._texts
        old_metas = self._metas

        # Rebuild with kept entries
        self._texts = [old_texts[i] for i in keep]
        self._metas = [old_metas[i] for i in keep]

        # Rebuild FAISS index
        if self._dim > 0 and self._texts:
            faiss = self._require_faiss()
            import numpy as np

            self._index = faiss.IndexFlatIP(self._dim)
            vecs = self._reconstruct_all_before_rebuild(keep)
            if vecs is not None:
                arr = np.array(vecs, dtype="float32")
                self._index.add(arr)
        else:
            self._index = None

        return removed

    def _reconstruct_all_before_rebuild(
        self, keep: list[int]
    ) -> list[list[float]] | None:
        """Reconstruct kept vectors from the current FAISS index."""
        if self._index is None:
            return None
        import numpy as np

        try:
            result: list[list[float]] = []
            for i in keep:
                vec = self._index.reconstruct(i)  # type: ignore[union-attr]
                result.append(vec.tolist())
            return result
        except Exception:
            return None

    # ── read ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._texts)

    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        if self._index is None or self.count() == 0:
            return []

        import numpy as np

        k = min(top_k, self.count())
        normed = _normalize(query_vector)
        q = np.array([normed], dtype="float32")
        distances, indices = self._index.search(q, k)  # type: ignore[union-attr]
        result: list[tuple[int, float]] = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx < 0:
                continue
            score = float(max(0.0, min(1.0, dist)))
            result.append((int(idx), score))
        return result

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        return self._texts[idx], self._metas[idx]

    def get_vector_at(self, idx: int) -> list[float]:
        if self._index is None:
            return []
        try:
            vec = self._index.reconstruct(idx)  # type: ignore[union-attr]
            return list(map(float, vec))
        except Exception:
            return []

    def all_texts(self) -> list[str]:
        return list(self._texts)

    # ── persistence ────────────────────────────────────────────────────────

    def persist(self, base_path: Path) -> None:
        faiss = self._require_faiss()
        faiss_path = Path(str(base_path) + _FAISS_SUFFIX)
        meta_path = Path(str(base_path) + _META_SUFFIX)
        faiss_path.parent.mkdir(parents=True, exist_ok=True)

        if self._index is not None:
            faiss.write_index(self._index, str(faiss_path))

        meta = [{"text": t, "metadata": m} for t, m in zip(self._texts, self._metas, strict=False)]
        with gzip.open(meta_path, "wt", encoding="utf-8") as fh:
            json.dump({"dim": self._dim, "meta": meta}, fh)

    @classmethod
    def load(cls, base_path: Path) -> FAISSVectorStore:
        store = cls()
        faiss_path = Path(str(base_path) + _FAISS_SUFFIX)
        meta_path = Path(str(base_path) + _META_SUFFIX)

        if not faiss_path.exists() or not meta_path.exists():
            return store

        faiss = store._require_faiss()
        store._index = faiss.read_index(str(faiss_path))

        with gzip.open(meta_path, "rt", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)

        store._dim = int(data.get("dim", 0))
        for item in data.get("meta", []):
            store._texts.append(str(item["text"]))
            store._metas.append(dict(item.get("metadata", {})))

        return store

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return (
            Path(str(base_path) + _FAISS_SUFFIX).exists()
            and Path(str(base_path) + _META_SUFFIX).exists()
        )

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        Path(str(base_path) + _FAISS_SUFFIX).unlink(missing_ok=True)
        Path(str(base_path) + _META_SUFFIX).unlink(missing_ok=True)

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        for suffix in (_FAISS_SUFFIX, _META_SUFFIX):
            old = Path(str(old_base) + suffix)
            new = Path(str(new_base) + suffix)
            if old.exists():
                old.rename(new)
