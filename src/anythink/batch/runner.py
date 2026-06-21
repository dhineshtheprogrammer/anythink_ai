"""Batch processing mode for Anythink."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage, TokenUsage

if TYPE_CHECKING:
    from anythink.app.context import AppContext

_MAX_PARALLEL = 20


@dataclass
class BatchResult:
    """Result for a single prompt in a batch run."""

    index: int
    prompt: str
    response: str
    usage: TokenUsage | None
    error: str | None
    elapsed_s: float


async def _run_single_prompt(
    ctx: AppContext,
    index: int,
    prompt: str,
    alias_name: str | None,
    system_prompt: str | None,
) -> BatchResult:
    """Run one prompt and return a BatchResult."""
    alias_key = alias_name or ctx.config.default_model_alias
    alias = ctx.model_registry.get(alias_key or "") if alias_key else None

    if alias is None:
        return BatchResult(
            index=index,
            prompt=prompt,
            response="",
            usage=None,
            error="No model alias configured. Set a default or pass --alias.",
            elapsed_s=0.0,
        )

    messages: list[ChatMessage] = []
    if system_prompt:
        messages.append(ChatMessage(role="system", content=system_prompt))
    messages.append(ChatMessage(role="user", content=prompt))

    try:
        api_key = ctx.key_manager.get_key(alias.provider)
        prov_cls = ctx.provider_registry.get(alias.provider)
        if prov_cls is None:
            return BatchResult(
                index=index,
                prompt=prompt,
                response="",
                usage=None,
                error=f"Provider '{alias.provider}' not registered.",
                elapsed_s=0.0,
            )
        provider = prov_cls(api_key=api_key)

        start = time.monotonic()
        full_text = ""
        final_usage: TokenUsage | None = None

        async for chunk in provider.stream_chat(
            messages,
            alias.model_id,
            gen_params=alias.gen_params,
        ):
            full_text += chunk.text
            if chunk.usage is not None:
                final_usage = chunk.usage

        return BatchResult(
            index=index,
            prompt=prompt,
            response=full_text,
            usage=final_usage,
            error=None,
            elapsed_s=time.monotonic() - start,
        )

    except Exception as e:
        return BatchResult(
            index=index,
            prompt=prompt,
            response="",
            usage=None,
            error=str(e),
            elapsed_s=0.0,
        )


async def run_batch(
    ctx: AppContext,
    prompts: list[str],
    *,
    parallel: int = 1,
    alias: str | None = None,
    system_prompt: str | None = None,
) -> list[BatchResult]:
    """Run a list of prompts and return results in original order.

    ``parallel`` is capped at _MAX_PARALLEL to avoid rate-limit hammering.
    """
    capped = max(1, min(parallel, _MAX_PARALLEL))
    semaphore = asyncio.Semaphore(capped)

    async def _guarded(idx: int, prompt: str) -> BatchResult:
        async with semaphore:
            return await _run_single_prompt(ctx, idx, prompt, alias, system_prompt)

    tasks = [_guarded(i, p) for i, p in enumerate(prompts)]
    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda r: r.index)
