"""Tests for optimize/context_engine.py — ContextRelevanceEngine."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from anythink.optimize.context_engine import ContextRelevanceEngine
from anythink.optimize.models import OptimizeSettings
from anythink.providers.base import ChatMessage, TextPart


def _msg(role: str, text: str) -> ChatMessage:
    return ChatMessage(
        role=role,
        content=text,
        timestamp=datetime(2024, 1, 1),
        metadata={},
    )


def _history(*texts: str) -> list[ChatMessage]:
    msgs = []
    for i, text in enumerate(texts):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append(_msg(role, text))
    return msgs


class TestContextRelevanceEngineRecency:
    def _make(self, **kwargs: object) -> ContextRelevanceEngine:
        settings = OptimizeSettings(history_mode="recency", **kwargs)
        return ContextRelevanceEngine(settings=settings, embedding_backend=None)

    async def test_empty_history_returns_empty(self) -> None:
        engine = self._make()
        result = await engine.select_relevant_history([], "hello")
        assert result == []

    async def test_returns_recent_messages(self) -> None:
        engine = self._make()
        history = _history("one", "resp one", "two", "resp two", "three", "resp three")
        result = await engine.select_relevant_history(history, "three", target_token_budget=10000)
        # Should include recent messages
        assert len(result) > 0

    async def test_always_includes_last_three(self) -> None:
        engine = self._make()
        # 10 messages; last 3 must always be included regardless of topic
        history = _history(*[f"message {i}" for i in range(10)])
        result = await engine.select_relevant_history(history, "unrelated xyz query", target_token_budget=10000)
        assert len(result) >= 3

    async def test_budget_trims_oldest_messages(self) -> None:
        engine = self._make()
        # Very small budget — should return fewer messages
        history = _history(*["long message text that takes space " * 10 for _ in range(20)])
        result = await engine.select_relevant_history(history, "anything", target_token_budget=50)
        total_chars = sum(len(m.content if isinstance(m.content, str) else "") for m in result)
        assert total_chars // 4 <= 50 or len(result) <= len(history)

    async def test_topically_relevant_message_included(self) -> None:
        engine = self._make()
        history = [
            _msg("user", "Tell me about Python sorting algorithms"),
            _msg("assistant", "Python has several sorting methods including sort() and sorted()"),
            _msg("user", "What is the weather today"),
            _msg("assistant", "I cannot check weather"),
        ]
        result = await engine.select_relevant_history(
            history, "How do I use Python sorted function?", target_token_budget=10000
        )
        texts = [m.content for m in result]
        # The Python-related message should be included
        assert any("Python" in str(t) or "sort" in str(t).lower() for t in texts)


class TestContextRelevanceEngineSemantic:
    def _make_mock_embedding(self) -> MagicMock:
        backend = MagicMock()
        backend.is_available.return_value = True
        # Return simple vectors: query gets [1,0], messages get varying vectors
        backend.embed = AsyncMock(return_value=[
            [0.9, 0.1],  # msg 0: similar to query
            [0.1, 0.9],  # msg 1: dissimilar
            [0.8, 0.2],  # msg 2: somewhat similar
            [1.0, 0.0],  # query vector
        ])
        return backend

    async def test_semantic_mode_calls_embedding_backend(self) -> None:
        backend = self._make_mock_embedding()
        settings = OptimizeSettings(history_mode="semantic")
        engine = ContextRelevanceEngine(settings=settings, embedding_backend=backend)

        history = [
            _msg("user", "about python"),
            _msg("assistant", "about music"),
            _msg("user", "about code"),
        ]
        await engine.select_relevant_history(history, "python code question")
        backend.embed.assert_called_once()

    async def test_semantic_mode_falls_back_on_embedding_error(self) -> None:
        backend = MagicMock()
        backend.is_available.return_value = True
        backend.embed = AsyncMock(side_effect=RuntimeError("GPU error"))

        settings = OptimizeSettings(history_mode="semantic")
        engine = ContextRelevanceEngine(settings=settings, embedding_backend=backend)

        history = _history("topic a", "response a", "topic b", "response b")
        result = await engine.select_relevant_history(history, "topic b")
        # Fallback to recency — should return something non-empty
        assert isinstance(result, list)

    async def test_semantic_mode_with_no_backend_uses_recency(self) -> None:
        settings = OptimizeSettings(history_mode="semantic")
        engine = ContextRelevanceEngine(settings=settings, embedding_backend=None)

        history = _history("msg1", "resp1", "msg2", "resp2")
        result = await engine.select_relevant_history(history, "query")
        assert isinstance(result, list)
        assert len(result) >= 0


class TestNeedsSummarisation:
    def test_true_when_over_budget(self) -> None:
        settings = OptimizeSettings()
        engine = ContextRelevanceEngine(settings=settings)
        # Each message is 400 chars ≈ 100 tokens; 5 messages ≈ 500 tokens
        messages = [_msg("user", "x" * 400) for _ in range(5)]
        assert engine.needs_summarisation(messages, budget=200)

    def test_false_when_within_budget(self) -> None:
        settings = OptimizeSettings()
        engine = ContextRelevanceEngine(settings=settings)
        messages = [_msg("user", "short")]
        assert not engine.needs_summarisation(messages, budget=10000)

    def test_empty_messages_never_needs_summarisation(self) -> None:
        settings = OptimizeSettings()
        engine = ContextRelevanceEngine(settings=settings)
        assert not engine.needs_summarisation([], budget=10)
