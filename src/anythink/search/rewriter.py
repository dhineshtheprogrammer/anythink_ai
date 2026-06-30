"""AI-powered search query rewriter using the active session LLM."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.providers.base import BaseProvider

_REWRITE_SYSTEM = (
    "You are a search query optimizer. "
    "Given a user message, output ONLY a concise web search query (max 15 words). "
    "No preamble, no explanation, no punctuation at the end. "
    "Resolve references to prior context if provided. "
    "For complex questions output 2-3 queries separated by newlines."
)

_TIMEOUT_S = 5.0


class QueryRewriter:
    """Use the active LLM to produce optimized web search queries.

    Falls back to the original raw input on any error or timeout.
    """

    def __init__(self, provider: BaseProvider, model_id: str) -> None:
        self._provider = provider
        self._model_id = model_id

    async def rewrite(self, raw: str, history_context: str = "") -> str:
        """Return a single optimized query string. Falls back to *raw* on failure."""
        queries = await self.rewrite_multi(raw, history_context)
        return queries[0] if queries else raw

    async def rewrite_multi(self, raw: str, history_context: str = "") -> list[str]:
        """Return 1–3 optimized query strings. Falls back to [raw] on failure."""
        try:
            result = await asyncio.wait_for(
                self._call_llm(raw, history_context), timeout=_TIMEOUT_S
            )
            lines = [line.strip() for line in result.splitlines() if line.strip()]
            return lines[:3] if lines else [raw]
        except Exception:
            return [raw]

    async def _call_llm(self, raw: str, history_context: str) -> str:
        from anythink.providers.base import ChatMessage

        user_text = raw
        if history_context:
            user_text = f"Context:\n{history_context}\n\nUser message: {raw}"

        messages = [
            ChatMessage(role="system", content=_REWRITE_SYSTEM),
            ChatMessage(role="user", content=user_text),
        ]
        collected: list[str] = []
        async for chunk in self._provider.stream_chat(messages, self._model_id):
            if hasattr(chunk, "text"):
                collected.append(chunk.text)
        return "".join(collected).strip()
