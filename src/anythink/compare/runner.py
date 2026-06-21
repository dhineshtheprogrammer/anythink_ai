"""Multi-model comparison runner for Anythink."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage, TokenUsage

if TYPE_CHECKING:
    from anythink.app.context import AppContext


@dataclass
class CompareResult:
    """Result from a single model in a comparison run."""

    alias: str
    provider_name: str
    model_id: str
    text: str
    usage: TokenUsage | None
    cost_usd: float
    elapsed_s: float
    error: str | None = None


async def _run_single(
    ctx: AppContext,
    alias_name: str,
    messages: list[ChatMessage],
    timeout: float,
) -> CompareResult:
    """Stream a single model's response and collect the full text."""
    from anythink.spend.pricing import estimate_cost

    alias = ctx.model_registry.get(alias_name)
    if alias is None:
        return CompareResult(
            alias=alias_name,
            provider_name="unknown",
            model_id="unknown",
            text="",
            usage=None,
            cost_usd=0.0,
            elapsed_s=0.0,
            error=f"Alias '{alias_name}' not found",
        )

    try:
        api_key = ctx.key_manager.get_key(alias.provider)
        prov_cls = ctx.provider_registry.get(alias.provider)
        if prov_cls is None:
            return CompareResult(
                alias=alias_name,
                provider_name=alias.provider,
                model_id=alias.model_id,
                text="",
                usage=None,
                cost_usd=0.0,
                elapsed_s=0.0,
                error=f"Provider '{alias.provider}' not registered",
            )
        provider = prov_cls(api_key=api_key)

        start = time.monotonic()
        full_text = ""
        final_usage: TokenUsage | None = None

        async def _collect() -> None:
            nonlocal full_text, final_usage
            async for chunk in provider.stream_chat(
                messages,
                alias.model_id,
                gen_params=alias.gen_params,
            ):
                full_text += chunk.text
                if chunk.usage is not None:
                    final_usage = chunk.usage

        await asyncio.wait_for(_collect(), timeout=timeout)
        elapsed = time.monotonic() - start
        cost = estimate_cost(alias.provider, alias.model_id, final_usage) if final_usage else 0.0
        return CompareResult(
            alias=alias_name,
            provider_name=alias.provider,
            model_id=alias.model_id,
            text=full_text,
            usage=final_usage,
            cost_usd=cost,
            elapsed_s=elapsed,
        )

    except TimeoutError:
        return CompareResult(
            alias=alias_name,
            provider_name=alias.provider if alias else "unknown",
            model_id=alias.model_id if alias else "unknown",
            text="",
            usage=None,
            cost_usd=0.0,
            elapsed_s=timeout,
            error=f"Timed out after {timeout:.0f}s",
        )
    except Exception as e:
        return CompareResult(
            alias=alias_name,
            provider_name=alias.provider if alias else "unknown",
            model_id=alias.model_id if alias else "unknown",
            text="",
            usage=None,
            cost_usd=0.0,
            elapsed_s=0.0,
            error=str(e),
        )


async def run_comparison(
    ctx: AppContext,
    aliases: list[str],
    messages: list[ChatMessage],
    *,
    timeout: float = 60.0,
    max_concurrent: int = 3,
) -> list[CompareResult]:
    """Run the same prompt against multiple model aliases in parallel.

    Errors in individual models don't abort the others.
    """
    semaphore = asyncio.Semaphore(min(max_concurrent, len(aliases)))

    async def _guarded(alias: str) -> CompareResult:
        async with semaphore:
            return await _run_single(ctx, alias, messages, timeout)

    tasks = [_guarded(alias) for alias in aliases]
    return list(await asyncio.gather(*tasks))
