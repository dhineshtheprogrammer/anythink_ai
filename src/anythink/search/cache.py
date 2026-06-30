"""In-session search result cache with exact and semantic similarity matching."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from anythink.search.base import SearchResult

_SEMANTIC_THRESHOLD = 0.85


@dataclass
class _CacheEntry:
    results: list[SearchResult]
    query: str
    backend: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = Counter(tokens)
    total = max(len(tokens), 1)
    return {t: (count / total) * idf.get(t, 1.0) for t, count in tf.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class SearchCache:
    """In-memory per-session cache with TTL, exact match, and TF-IDF semantic match."""

    def __init__(self, ttl_minutes: int = 30, max_entries: int = 100) -> None:
        self._ttl_seconds = ttl_minutes * 60
        self._max_entries = max_entries
        self._entries: list[_CacheEntry] = []

    def get(self, query: str, backend: str) -> list[SearchResult] | None:
        """Return cached results or None. Checks exact match first, then semantic."""
        self.evict_expired()
        key = query.lower().strip()

        # Exact match
        for entry in self._entries:
            if entry.backend == backend and entry.query.lower().strip() == key:
                return list(entry.results)

        # Semantic match
        match = self._semantic_match(query, backend)
        if match is not None:
            return list(match.results)
        return None

    def put(self, query: str, backend: str, results: list[SearchResult]) -> None:
        """Store results. Evicts LRU entry if at capacity."""
        self.evict_expired()
        if len(self._entries) >= self._max_entries:
            self._entries.pop(0)
        self._entries.append(_CacheEntry(results=list(results), query=query, backend=backend))

    def evict_expired(self) -> int:
        """Remove expired entries; returns count removed."""
        now = datetime.now(timezone.utc)
        before = len(self._entries)
        self._entries = [
            e
            for e in self._entries
            if (now - e.created_at).total_seconds() < self._ttl_seconds
        ]
        return before - len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def status(self) -> dict[str, object]:
        """Return cache stats."""
        if not self._entries:
            return {"entries": 0, "oldest_age_s": None}
        now = datetime.now(timezone.utc)
        oldest = max((now - e.created_at).total_seconds() for e in self._entries)
        return {"entries": len(self._entries), "oldest_age_s": round(oldest, 1)}

    def _semantic_match(self, query: str, backend: str) -> _CacheEntry | None:
        candidates = [e for e in self._entries if e.backend == backend]
        if not candidates:
            return None

        # Build IDF from all cached queries
        all_tokens = [_tokenize(e.query) for e in candidates]
        doc_count = len(all_tokens)
        df: Counter[str] = Counter()
        for toks in all_tokens:
            df.update(set(toks))
        idf = {t: math.log(doc_count / (df[t] + 1)) + 1 for t in df}

        query_vec = _tfidf_vector(_tokenize(query), idf)
        best_score = 0.0
        best_entry: _CacheEntry | None = None
        for entry, toks in zip(candidates, all_tokens, strict=True):
            entry_vec = _tfidf_vector(toks, idf)
            score = _cosine(query_vec, entry_vec)
            if score > best_score:
                best_score = score
                best_entry = entry

        return best_entry if best_score >= _SEMANTIC_THRESHOLD else None
