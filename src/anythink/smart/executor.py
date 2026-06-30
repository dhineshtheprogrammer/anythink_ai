"""SequentialExecutor — runs MMAE specialist models one by one."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage, GenerationParams
from anythink.smart.models import RoutingPlan, SpecialistResponse
from anythink.smart.quality import QualityGate
from anythink.smart.store import TemporaryResponseStore

if TYPE_CHECKING:
    from anythink.config.models import ModelRegistry
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.smart.models import SubQuestion
    from anythink.smart.registry import SmartRegistry

_SPECIALIST_SYSTEM_TEMPLATE = """\
You are a specialist assistant optimised for {category_name} tasks.
Answer the task given to you concisely and accurately.
Use your full capability for this specific domain.
"""


def _build_specialist_messages(
    sub_question: SubQuestion,
    original_message: str,
    history: list[ChatMessage],
    category_name: str,
) -> list[ChatMessage]:
    """Build the full message list for a specialist call (spec section 9.3 order)."""
    system = ChatMessage(
        role="system",
        content=_SPECIALIST_SYSTEM_TEMPLATE.format(category_name=category_name),
    )
    # Recent history tail — last 5 turns
    tail = history[-10:] if len(history) > 10 else list(history)
    # Remove any existing system messages from tail to avoid duplication
    tail = [m for m in tail if m.role != "system"]

    user_task = ChatMessage(
        role="user",
        content=(
            f"[ORIGINAL QUESTION]\n{original_message}\n\n"
            f"[YOUR TASK]\n{sub_question.sub_question}"
        ),
    )
    return [system, *tail, user_task]


class SequentialExecutor:
    """Runs specialist models one after another, applying the quality gate.

    Retry chain (spec section 12.3):
    1. Same model, once.
    2. Secondary aliases for the same category from the registry.
    3. General fallback model.
    4. Accept with low_confidence=True.
    """

    def __init__(
        self,
        registry: SmartRegistry,
        quality_gate: QualityGate,
        provider_registry: ProviderRegistry,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
    ) -> None:
        self._registry = registry
        self._gate = quality_gate
        self._provider_registry = provider_registry
        self._model_registry = model_registry
        self._key_manager = key_manager

    async def execute(
        self,
        routing_plan: RoutingPlan,
        original_message: str,
        history: list[ChatMessage],
        store: TemporaryResponseStore,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> None:
        """Run all specialists from the routing plan sequentially.

        Appends each SpecialistResponse to store in order. Calls on_progress
        with (status_message, current_slot, total_slots) before each specialist.
        """
        total = len(routing_plan.routing_plan)
        for slot_idx, sq in enumerate(routing_plan.routing_plan, start=1):
            if on_progress:
                with contextlib.suppress(Exception):
                    on_progress(
                        f"Running {sq.category} specialist ({slot_idx}/{total})…",
                        slot_idx,
                        total,
                    )

            result = await self._run_specialist(sq, slot_idx, original_message, history)
            store.add(result)

    async def _run_specialist(
        self,
        sq: SubQuestion,
        slot: int,
        original_message: str,
        history: list[ChatMessage],
    ) -> SpecialistResponse:
        from anythink.smart.categories import CATEGORIES

        cat = CATEGORIES.get(sq.category)
        category_name = cat.name if cat else sq.category

        messages = _build_specialist_messages(sq, original_message, history, category_name)

        # Ordered alias candidates for this category
        primary_alias = sq.model_alias or self._registry.get(sq.category) or ""
        candidates = self._build_candidates(sq.category, primary_alias)

        retry_count = 0
        last_result: SpecialistResponse | None = None

        for alias_name in candidates:
            for attempt in range(2):  # try each alias at most twice (spec layer 1 = retry same)
                t0 = time.monotonic()
                response_text = await self._call_alias(alias_name, messages)
                duration_s = time.monotonic() - t0

                check = self._gate.evaluate(response_text, sq.category, sq.sub_question)
                candidate_result = SpecialistResponse(
                    slot=slot,
                    category=sq.category,
                    model_alias=alias_name,
                    sub_question=sq.sub_question,
                    response=response_text,
                    quality_score=check.score,
                    retry_count=retry_count,
                    duration_s=duration_s,
                    low_confidence=False,
                )

                if check.passed:
                    return candidate_result

                retry_count += 1
                last_result = candidate_result
                # Only retry same model once (attempt == 0 → retry; attempt == 1 → move on)
                if attempt == 0:
                    continue
                break  # move to next alias

        # All candidates exhausted — accept last result with low_confidence flag
        if last_result is not None:
            last_result.low_confidence = True
            return last_result

        # Should not reach here, but guard against empty candidate list
        return SpecialistResponse(
            slot=slot,
            category=sq.category,
            model_alias=sq.model_alias or "unknown",
            sub_question=sq.sub_question,
            response="(no response produced)",
            quality_score=0,
            retry_count=retry_count,
            duration_s=0.0,
            low_confidence=True,
        )

    def _build_candidates(self, category: str, primary_alias: str) -> list[str]:
        """Return ordered alias names to try for this category."""
        candidates: list[str] = []
        if primary_alias:
            candidates.append(primary_alias)

        # Secondary candidates: all aliases registered for this category other than primary
        cat_alias = self._registry.get(category)
        if cat_alias and cat_alias not in candidates:
            candidates.append(cat_alias)

        # General fallback (spec layer 3)
        general_alias = self._registry.get("general")
        if general_alias and general_alias not in candidates:
            candidates.append(general_alias)

        # Last resort: first available model alias
        if not candidates:
            all_aliases = self._model_registry.list_all()
            if all_aliases:
                candidates.append(all_aliases[0].alias)

        return candidates

    async def _call_alias(self, alias_name: str, messages: list[ChatMessage]) -> str:
        alias_obj = self._model_registry.get(alias_name)
        if alias_obj is None:
            # Alias not found — try the first available model
            all_aliases = self._model_registry.list_all()
            if not all_aliases:
                return "(no models available)"
            alias_obj = all_aliases[0]

        api_key = self._key_manager.get_key(alias_obj.provider)
        provider = self._provider_registry.instantiate(alias_obj.provider, api_key=api_key)
        gen_params = GenerationParams(temperature=0.3, max_tokens=2048)

        chunks: list[str] = []
        async for chunk in provider.stream_chat(
            messages=messages,
            model=alias_obj.model_id,
            gen_params=gen_params,
        ):
            chunks.append(chunk.text)
        return "".join(chunks)
