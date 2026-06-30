"""StageOutputOptimizer — transforms stage outputs into optimal inputs for the next stage."""

from __future__ import annotations

import json
from typing import Any

from anythink.workflow.models import Stage, StageResult, StageType, WorkflowState


class StageOutputOptimizer:
    """Transforms the output of a completed stage into the best possible input
    for the following stage.

    The optimizer never discards content that might be relevant. When in doubt
    about relevance, it includes rather than excludes. Only clearly irrelevant
    metadata (timing, internal stage numbers, debug markers) is stripped.

    All methods are synchronous and pure — no I/O, no external calls.
    """

    def transform(
        self,
        result: StageResult,
        next_stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Return the optimized context dict for *next_stage*.

        The returned dict always contains at least:
        - ``"content"``: the primary text payload for the next stage
        - ``"output"``: the raw named-field dict from the completed stage
        - ``"refs"``: resolved values of *next_stage.input_refs*
        """
        raw_context = {
            "output": result.output,
            "raw_content": result.raw_content,
            "refs": self._resolve_refs(next_stage.input_refs, state),
        }

        dispatch = {
            StageType.LLM_SPECIALIST: self._for_llm,
            StageType.MCP_CALL: self._for_mcp,
            StageType.FORMATTER: self._for_formatter,
            StageType.LOOP: self._for_loop,
            StageType.USER_APPROVAL: self._for_approval,
            StageType.CONDITION: self._for_condition,
        }

        handler = dispatch.get(next_stage.type)
        if handler:
            return handler(raw_context, next_stage, state)
        return raw_context

    # ------------------------------------------------------------------
    # Per-stage-type transformations
    # ------------------------------------------------------------------

    def _for_llm(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Prepend a concise task instruction to the content payload."""
        # Build the primary content from refs or raw_content
        primary = self._primary_text(ctx)

        instruction = stage.task_instruction or (
            f"Process the following input and produce the requested output."
        )
        format_hint = (
            f" Respond in {stage.expected_format} format." if stage.expected_format else ""
        )

        return {
            **ctx,
            "content": f"{instruction}{format_hint}\n\n{primary}",
            "instruction": instruction,
        }

    def _for_mcp(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Extract and resolve MCP tool parameters from upstream output."""
        resolved_params: dict[str, Any] = dict(stage.tool_params)

        # Resolve any template placeholders in params: {{stage_N.field}}
        refs = ctx.get("refs", {})
        for key, value in list(resolved_params.items()):
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                ref_key = value[2:-2].strip()
                resolved = refs.get(ref_key) or state.resolve_ref(ref_key)
                if resolved is not None:
                    resolved_params[key] = resolved

        return {
            **ctx,
            "content": self._primary_text(ctx),
            "resolved_params": resolved_params,
        }

    def _for_formatter(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Pass format hints and detect the incoming content type."""
        primary = self._primary_text(ctx)
        content_type = self._detect_content_type(primary)

        return {
            **ctx,
            "content": primary,
            "target_format": stage.expected_format or "markdown",
            "source_content_type": content_type,
        }

    def _for_loop(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Resolve the input collection and prepare the per-iteration context."""
        if stage.loop_def is None:
            return {**ctx, "content": self._primary_text(ctx), "collection": []}

        ref = stage.loop_def.input_collection_ref
        collection = state.resolve_ref(ref)

        # Try the refs dict too
        if collection is None:
            collection = ctx.get("refs", {}).get(ref)

        # Fall back to the raw output field
        if collection is None:
            collection = ctx.get("output", {})

        if not isinstance(collection, list):
            collection = [collection] if collection is not None else []

        return {
            **ctx,
            "content": self._primary_text(ctx),
            "collection": collection,
            "collection_ref": ref,
            "accumulation_strategy": stage.loop_def.accumulation_strategy.value,
        }

    def _for_approval(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Include the approval message and a summary of completed stages."""
        completed_summary = ", ".join(
            f"{r.stage_id}({r.stage_type.value})" for r in state.completed_stages[-3:]
        )
        return {
            **ctx,
            "content": stage.approval_message or "Proceed?",
            "completed_summary": completed_summary,
        }

    def _for_condition(
        self,
        ctx: dict[str, Any],
        stage: Stage,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Provide the condition expression and the full accumulated results."""
        return {
            **ctx,
            "content": self._primary_text(ctx),
            "condition_expr": stage.condition_expr,
            "accumulated_results": dict(state.accumulated_results),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_refs(
        self,
        input_refs: list[str],
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Resolve a list of dot-path refs against the accumulated results."""
        return {ref: state.resolve_ref(ref) for ref in input_refs if state.resolve_ref(ref) is not None}

    def _primary_text(self, ctx: dict[str, Any]) -> str:
        """Return the best single text payload from the context dict."""
        # Prefer resolved refs if they contain text
        refs = ctx.get("refs", {})
        if refs:
            texts = [str(v) for v in refs.values() if v is not None]
            if texts:
                return "\n\n".join(texts)

        # Fall back to raw_content
        raw = ctx.get("raw_content", "")
        if raw:
            return raw

        # Fall back to serialised output dict
        output = ctx.get("output", {})
        if output:
            return json.dumps(output, indent=2, default=str)

        return ""

    def _detect_content_type(self, text: str) -> str:
        """Heuristically detect whether the text is structured or prose."""
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return "json"
        if "," in stripped and "\n" in stripped[:200]:
            return "csv"
        if stripped.startswith("#") or "**" in stripped or "- " in stripped[:100]:
            return "markdown"
        return "prose"
