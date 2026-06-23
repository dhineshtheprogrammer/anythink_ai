"""Context relevance engine — history selection for MMOS queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.optimize.models import OptimizeSettings

if TYPE_CHECKING:
    from anythink.embeddings.base import BaseEmbeddingBackend
    from anythink.providers.base import ChatMessage

_CHARS_PER_TOKEN = 4  # rough estimate used for budget checks


def _content_to_text(content: str | list[object]) -> str:
    """Extract plain text from a ChatMessage content field."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        text = getattr(part, "text", None)
        if text:
            parts.append(str(text))
    return " ".join(parts)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ContextRelevanceEngine:
    """Selects the most relevant history messages for the current query.

    Three modes (configured in OptimizeSettings.history_mode):
    - "semantic"     : embed query + messages; pick top-K by cosine similarity
    - "recency"      : take last N messages; filter by topic keyword overlap
    - "model_decides": a fast model picks relevant message indices (future)
    """

    _RECENCY_MAX_MESSAGES = 8
    _SEMANTIC_TOP_K = 6
    _SEMANTIC_THRESHOLD = 0.35

    def __init__(
        self,
        settings: OptimizeSettings,
        embedding_backend: BaseEmbeddingBackend | None = None,
    ) -> None:
        self._settings = settings
        self._emb = embedding_backend

    # ── Public API ────────────────────────────────────────────────────────

    async def select_relevant_history(
        self,
        history: list[ChatMessage],
        current_query: str,
        target_token_budget: int | None = None,
    ) -> list[ChatMessage]:
        """Return a subset of *history* relevant to *current_query*."""
        budget = target_token_budget or self._settings.history_max_tokens

        if not history:
            return []

        mode = self._settings.history_mode

        if mode == "semantic" and self._emb is not None and self._emb.is_available():
            selected = await self._semantic_similarity(
                history, current_query, self._SEMANTIC_TOP_K, budget
            )
        else:
            # "recency" mode, "model_decides" (future), or semantic with no backend
            selected = self._recency_topic(
                history, current_query, self._RECENCY_MAX_MESSAGES, budget
            )

        return selected

    def needs_summarisation(
        self,
        messages: list[ChatMessage],
        budget: int,
    ) -> bool:
        """Return True if the selected messages exceed *budget* tokens."""
        return self._estimate_tokens(messages) > budget

    # ── History selection modes ───────────────────────────────────────────

    def _recency_topic(
        self,
        history: list[ChatMessage],
        query: str,
        max_messages: int,
        budget: int,
    ) -> list[ChatMessage]:
        """Take recent messages and filter out off-topic ones."""
        recent = history[-max_messages:]

        query_words = set(query.lower().split())

        def is_topically_relevant(msg: ChatMessage) -> bool:
            text = _content_to_text(msg.content).lower()
            msg_words = set(text.split())
            overlap = len(query_words & msg_words)
            return overlap >= 2

        # Always include the last 3 messages regardless of topic
        must_include = {id(m) for m in recent[-3:]}
        selected = [
            m for m in recent if id(m) in must_include or is_topically_relevant(m)
        ]

        return self._trim_to_budget(selected, budget)

    async def _semantic_similarity(
        self,
        history: list[ChatMessage],
        query: str,
        top_k: int,
        budget: int,
    ) -> list[ChatMessage]:
        """Use embeddings to select the top-K most similar messages."""
        assert self._emb is not None

        texts = [_content_to_text(m.content) for m in history]
        all_texts = texts + [query]

        try:
            vectors = await self._emb.embed(all_texts)
        except Exception:
            # Embedding failure — fall back to recency
            return self._recency_topic(history, query, self._RECENCY_MAX_MESSAGES, budget)

        query_vec = vectors[-1]
        msg_vecs = vectors[:-1]

        scored = [
            (i, _cosine_similarity(query_vec, msg_vecs[i]))
            for i in range(len(history))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Keep messages above similarity threshold
        above_threshold = [
            (i, sim) for i, sim in scored if sim >= self._SEMANTIC_THRESHOLD
        ][:top_k]

        # Return in chronological order
        selected_indices = sorted(i for i, _ in above_threshold)
        selected = [history[i] for i in selected_indices]

        return self._trim_to_budget(selected, budget)

    # ── Utilities ─────────────────────────────────────────────────────────

    def _estimate_tokens(self, messages: list[ChatMessage]) -> int:
        """Rough token estimate for a list of messages."""
        total_chars = sum(len(_content_to_text(m.content)) for m in messages)
        return total_chars // _CHARS_PER_TOKEN

    def _trim_to_budget(
        self,
        messages: list[ChatMessage],
        budget: int,
    ) -> list[ChatMessage]:
        """Drop oldest messages until the token estimate fits within *budget*."""
        while messages and self._estimate_tokens(messages) > budget:
            messages = messages[1:]
        return messages
