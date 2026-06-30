"""LLM_SPECIALIST stage executor — streams a response from a specific model."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from anythink.providers.base import ChatMessage, GenerationParams
from anythink.workflow.models import StageResult, StageType

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.workflow.models import Stage, WorkflowCallbacks, WorkflowState


async def execute(
    stage: Stage,
    state: WorkflowState,
    ctx: AppContext,
    callbacks: WorkflowCallbacks,
) -> StageResult:
    """Execute an LLM_SPECIALIST stage with automatic fallback chain support."""
    start = time.monotonic()

    candidates = _build_candidate_chain(stage, ctx)
    if not candidates:
        return StageResult(
            stage_id=stage.id,
            stage_type=StageType.LLM_SPECIALIST,
            output={},
            raw_content="",
            duration_s=time.monotonic() - start,
            error="No model alias configured and no aliases available.",
        )

    content = _build_content(stage, state)
    last_error = ""
    tried: list[str] = []

    for candidate_alias in candidates:
        alias_obj = ctx.model_registry.get(candidate_alias)
        if alias_obj is None:
            tried.append(candidate_alias)
            last_error = f"Alias '{candidate_alias}' not found in model registry."
            continue

        tried.append(candidate_alias)
        fallback_used = len(tried) > 1

        try:
            api_key = ctx.key_manager.get_key(alias_obj.provider)
            provider = ctx.provider_registry.instantiate(alias_obj.provider, api_key=api_key)

            messages: list[ChatMessage] = [ChatMessage(role="user", content=content)]
            gen_params = GenerationParams(temperature=0.7, max_tokens=4096)

            chunks: list[str] = []
            last_usage = None
            async for chunk in provider.stream_chat(
                messages=messages,
                model=alias_obj.model_id,
                gen_params=gen_params,
            ):
                chunks.append(chunk.text)
                if chunk.usage:
                    last_usage = chunk.usage

            raw_content = "".join(chunks)

            if last_usage is not None:
                ctx.spend_tracker.record(
                    session_id="workflow",
                    model_id=alias_obj.model_id,
                    provider=alias_obj.provider,
                    usage=last_usage,
                )

            output: dict[str, Any] = (
                {stage.output_field: raw_content} if stage.output_field else {"result": raw_content}
            )

            return StageResult(
                stage_id=stage.id,
                stage_type=StageType.LLM_SPECIALIST,
                output=output,
                raw_content=raw_content,
                duration_s=time.monotonic() - start,
                model_alias=candidate_alias,
                fallback_used=fallback_used,
                fallback_chain=tried[:-1] if fallback_used else [],
            )

        except Exception as exc:
            last_error = str(exc)
            continue

    # All candidates exhausted
    return StageResult(
        stage_id=stage.id,
        stage_type=StageType.LLM_SPECIALIST,
        output={},
        raw_content="",
        duration_s=time.monotonic() - start,
        model_alias=candidates[0] if candidates else "",
        fallback_used=len(tried) > 1,
        fallback_chain=tried,
        error=last_error,
    )


def _build_candidate_chain(stage: Stage, ctx: AppContext) -> list[str]:
    """Return the ordered list of alias candidates: configured alias + fallbacks."""
    alias = stage.model_alias
    if alias:
        fallbacks = ctx.workflow_registry.get_fallback_chain(alias)
        candidates = [alias] + fallbacks
    else:
        # Auto-select: use all configured aliases as last-resort pool
        all_aliases = ctx.model_registry.list_all()
        candidates = [a.alias for a in all_aliases]
    return candidates


def _build_content(stage: Stage, state: WorkflowState) -> str:
    """Build the user-facing prompt text for the LLM."""
    parts: list[str] = []

    if stage.task_instruction:
        parts.append(stage.task_instruction)

    for ref in stage.input_refs:
        value = state.resolve_ref(ref)
        if value is not None:
            parts.append(str(value))

    if not parts and state.completed_stages:
        parts.append(state.completed_stages[-1].raw_content)

    return "\n\n".join(parts) if parts else "Please provide a response."
