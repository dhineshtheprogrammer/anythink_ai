"""Pure-Python BM25 (Okapi BM25) index for keyword-based RAG retrieval.

# mypy: disable-error-code="assignment,arg-type,attr-defined,call-overload"

BM25 formula per document d and query term q_i:

  BM25(d, Q) = Σ_i IDF(q_i) * f(q_i, d) * (k1 + 1)
                               ─────────────────────────────────────────
                               f(q_i, d) + k1 * (1 - b + b * |d| / avgdl)

  IDF(q) = log( (N - df + 0.5) / (df + 0.5) + 1 )

Parameters
----------
k1 : float
    Term saturation constant (1.5 by default).  Higher values increase the
    influence of term frequency without fully saturating at lower counts.
b  : float
    Length normalisation factor (0.75 by default).  1.0 = full normalisation
    by document length; 0.0 = no length normalisation.

No external dependencies — only stdlib math, re, json, gzip.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenization — strips punctuation, keeps alphanumeric tokens."""
    return re.findall(r"\b\w+\b", text.lower())


@dataclass
class BM25Index:
    """In-memory BM25 index with optional gzip-JSON persistence."""

    k1: float = 1.5
    b: float = 0.75

    # Internal state — populated by build()
    _n: int = field(default=0, init=False, repr=False)
    _avg_dl: float = field(default=0.0, init=False, repr=False)
    _doc_freqs: list[dict[str, int]] = field(default_factory=list, init=False, repr=False)
    _doc_lens: list[int] = field(default_factory=list, init=False, repr=False)
    _df: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    # ── build ──────────────────────────────────────────────────────────────────

    def build(self, corpus: list[str]) -> None:
        """Index *corpus* — a list of chunk texts in store order.

        Must be called before ``score()``.  Rebuilding replaces the previous index.
        """
        self._n = len(corpus)
        self._doc_freqs = []
        self._doc_lens = []
        self._df = {}
        total_tokens = 0

        for doc in corpus:
            tokens = _tokenize(doc)
            total_tokens += len(tokens)
            tf: dict[str, int] = {}
            for tok in tokens:
                tf[tok] = tf.get(tok, 0) + 1
            self._doc_freqs.append(tf)
            self._doc_lens.append(len(tokens))
            for tok in tf:
                self._df[tok] = self._df.get(tok, 0) + 1

        self._avg_dl = total_tokens / max(1, self._n)

    @property
    def is_built(self) -> bool:
        """True if ``build()`` has been called with at least one document."""
        return self._n > 0

    @property
    def corpus_size(self) -> int:
        """Number of documents in the index."""
        return self._n

    # ── query ──────────────────────────────────────────────────────────────────

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._n - df + 0.5) / (df + 0.5) + 1)

    def score(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Return ``(chunk_index, bm25_score)`` pairs for *top_k* best matches.

        Scores are un-normalised BM25 floats.  Call the caller-side normaliser
        before fusing with vector scores (see ``retrieval._normalize``).
        Returns an empty list if the index has not been built.
        """
        if not self.is_built:
            return []

        query_terms = set(_tokenize(query))
        scores: dict[int, float] = {}

        for term in query_terms:
            idf = self._idf(term)
            if idf == 0.0:
                continue
            for doc_idx, (tf, doc_len) in enumerate(
                zip(self._doc_freqs, self._doc_lens, strict=False)
            ):
                freq = tf.get(term, 0)
                if freq == 0:
                    continue
                numer = freq * (self.k1 + 1)
                denom = freq + self.k1 * (1 - self.b + self.b * doc_len / self._avg_dl)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + idf * numer / denom

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    # ── persistence ────────────────────────────────────────────────────────────

    def persist(self, path: Path) -> None:
        """Serialise to *path* as gzip-compressed JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "n": self._n,
            "avg_dl": self._avg_dl,
            "doc_freqs": self._doc_freqs,
            "doc_lens": self._doc_lens,
            "df": self._df,
        }
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(data, fh)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        """Deserialise a persisted index from *path*.

        Returns an empty index if *path* does not exist.
        """
        idx = cls()
        if not path.exists():
            return idx
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
        idx.k1 = float(data.get("k1", 1.5))
        idx.b = float(data.get("b", 0.75))
        idx._n = int(data.get("n", 0))
        idx._avg_dl = float(data.get("avg_dl", 0.0))
        idx._doc_freqs = [dict(d) for d in data.get("doc_freqs", [])]
        idx._doc_lens = [int(x) for x in data.get("doc_lens", [])]
        idx._df = {str(k): int(v) for k, v in data.get("df", {}).items()}
        return idx
