"""LanceDB vector store backend.

Requires ``pip install anythink[rag-lance]`` (lancedb>=0.6).

Storage layout:
  {base_path}.lance/  — LanceDB database directory (columnar Arrow format)

LanceDB supports native hybrid search and metadata filtering, making it
efficient for large indexes.  ``supports_metadata_filter()`` returns True.

Sequential integer indices are tracked via an ``_order`` list that records
insertion order, since LanceDB does not guarantee stable positional access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anythink.exceptions import RAGError
from anythink.rag.backends.base import BaseVectorStore

_SUFFIX = ".lance"
_TABLE = "chunks"


class LanceVectorStore(BaseVectorStore):
    """LanceDB-backed vector store with columnar storage and hybrid search."""

    def __init__(self) -> None:
        self._db: object | None = None
        self._table: object | None = None
        self._texts: list[str] = []
        self._metas: list[dict[str, Any]] = []
        self._vecs: list[list[float]] = []

    def is_available(self) -> bool:
        try:
            import lancedb  # noqa: F401

            return True
        except ImportError:
            return False

    def _require_lancedb(self) -> Any:
        try:
            import lancedb

            return lancedb
        except ImportError as exc:
            raise RAGError(
                "lancedb not installed.",
                user_message="LanceDB backend requires: pip install anythink[rag-lance]",
            ) from exc

    def _init_db(self, db_path: Path) -> None:
        lancedb = self._require_lancedb()
        db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(db_path))

    # ── write ──────────────────────────────────────────────────────────────

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        vectors: list[list[float]],
    ) -> None:
        if self._db is None or not texts:
            return

        import pyarrow as pa

        rows = [
            {
                "idx": len(self._texts) + i,
                "text": t,
                "vector": v,
                "metadata_json": json.dumps(m),
                "source_path": str(m.get("source_path", "")),
            }
            for i, (t, m, v) in enumerate(zip(texts, metadatas, vectors, strict=False))
        ]

        try:
            if self._table is None:
                self._table = self._db.create_table(_TABLE, data=rows, mode="overwrite")  # type: ignore[union-attr]
            else:
                self._table.add(rows)  # type: ignore[union-attr]
        except Exception as exc:
            raise RAGError(
                f"LanceDB add failed: {exc}",
                user_message="Failed to add chunks to LanceDB index.",
            ) from exc

        self._texts.extend(texts)
        self._metas.extend(metadatas)
        self._vecs.extend(vectors)

    def remove_by_source(self, source_path: str) -> int:
        if self._table is None:
            return 0
        try:
            escaped = source_path.replace("'", "\\'")
            self._table.delete(f"source_path = '{escaped}'")  # type: ignore[union-attr]
        except Exception:
            pass

        keep = [
            i for i, m in enumerate(self._metas)
            if str(m.get("source_path", "")) != source_path
        ]
        removed = len(self._metas) - len(keep)
        self._texts = [self._texts[i] for i in keep]
        self._metas = [self._metas[i] for i in keep]
        self._vecs = [self._vecs[i] for i in keep]
        return removed

    # ── read ───────────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self._texts)

    def query_ranked(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        if self._table is None or self.count() == 0:
            return []

        k = min(top_k, self.count())
        try:
            results = (
                self._table.search(query_vector)  # type: ignore[union-attr]
                .limit(k)
                .to_list()
            )
        except Exception:
            return []

        ranked: list[tuple[int, float]] = []
        for row in results:
            seq_idx = int(row.get("idx", -1))
            if seq_idx < 0 or seq_idx >= self.count():
                continue
            dist = float(row.get("_distance", 1.0))
            score = float(max(0.0, 1.0 - dist))
            ranked.append((seq_idx, score))

        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_chunk_at(self, idx: int) -> tuple[str, dict[str, Any]]:
        return self._texts[idx], self._metas[idx]

    def get_vector_at(self, idx: int) -> list[float]:
        return self._vecs[idx] if idx < len(self._vecs) else []

    def all_texts(self) -> list[str]:
        return list(self._texts)

    def supports_metadata_filter(self) -> bool:
        return True

    # ── persistence ────────────────────────────────────────────────────────

    def persist(self, base_path: Path) -> None:
        # LanceDB auto-persists on add; compact for optimal read performance.
        if self._table is not None:
            try:
                self._table.compact_files()  # type: ignore[union-attr]
            except Exception:
                pass

    @classmethod
    def load(cls, base_path: Path) -> LanceVectorStore:
        store = cls()
        db_path = Path(str(base_path) + _SUFFIX)
        if not db_path.exists():
            return store

        store._init_db(db_path)
        try:
            store._table = store._db.open_table(_TABLE)  # type: ignore[union-attr]
            rows = store._table.to_list()  # type: ignore[union-attr]
            rows.sort(key=lambda r: int(r.get("idx", 0)))
            for row in rows:
                store._texts.append(str(row.get("text", "")))
                store._metas.append(json.loads(str(row.get("metadata_json", "{}"))))
                store._vecs.append(list(map(float, row.get("vector", []))))
        except Exception:
            pass

        return store

    @classmethod
    def exists(cls, base_path: Path) -> bool:
        return Path(str(base_path) + _SUFFIX).exists()

    @classmethod
    def delete_files(cls, base_path: Path) -> None:
        import shutil

        p = Path(str(base_path) + _SUFFIX)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    @classmethod
    def rename_files(cls, old_base: Path, new_base: Path) -> None:
        old = Path(str(old_base) + _SUFFIX)
        new = Path(str(new_base) + _SUFFIX)
        if old.exists():
            old.rename(new)
