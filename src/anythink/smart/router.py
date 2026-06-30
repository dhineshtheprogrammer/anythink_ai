"""RouterModel — calls the router LLM and produces a RoutingPlan."""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any

from anythink.exceptions import SmartError
from anythink.providers.base import ChatMessage, GenerationParams
from anythink.smart.categories import CATEGORIES
from anythink.smart.models import RoutingPlan, SubQuestion

if TYPE_CHECKING:
    from anythink.config.models import ModelRegistry
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.smart.registry import SmartRegistry

_ROUTER_SYSTEM_PROMPT_TEMPLATE = """\
You are a query routing expert for a multi-model answering engine.

## Your Task
Analyse the user's question, identify all applicable categories, decide whether \
the question needs to be split into multiple sub-questions, and produce a routing \
plan as a JSON object.

## Rules
- Identify 1–{max_splits} categories. Never produce more than {max_splits} entries \
in routing_plan.
- Each sub-question must be self-contained and cover exactly one category's scope.
- Use semantic understanding — do not rely on keyword matching.
- Categories detected with low confidence should be omitted.
- If the question does not fit any specialist category, classify it as "general".
- Set complexity to "single" when only one category applies (no splitting needed).
- Set complexity to "multi" when two or more categories apply.

## Available Categories
{category_catalogue}

## Current Model Assignments
{model_assignments}

## Output Schema
Respond with ONLY a valid JSON object. No explanation text outside the JSON.
{{
  "complexity": "single" | "multi",
  "categories_detected": [<list of category keys>],
  "routing_plan": [
    {{
      "sub_question": "<rewritten sub-question optimised for this specialist>",
      "category": "<category key>",
      "model_alias": "<assigned model alias>",
      "context_included": true
    }}
  ],
  "reasoning_summary": "<brief explanation of routing decision — debug only>"
}}
"""

_MAX_RETRIES = 1


def _build_category_catalogue() -> str:
    lines = []
    for cat in CATEGORIES.values():
        lines.append(f"- **{cat.key}** ({cat.name}): {cat.description}")
    return "\n".join(lines)


def _build_model_assignments(registry: SmartRegistry) -> str:
    assignments = registry.all_assignments()
    lines = []
    for cat_key, alias in assignments.items():
        label = alias if alias else "(not assigned — use default model)"
        lines.append(f"- {cat_key}: {label}")
    return "\n".join(lines)


def _extract_json(raw: str) -> str:
    """Extract the first JSON object from raw LLM output."""
    raw = raw.strip()
    # Try direct parse first
    if raw.startswith("{"):
        return raw
    # Look for a JSON block in markdown code fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        return m.group(1)
    # Fall back: find the first { … } span
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    raise SmartError(
        f"Router returned no JSON object. Raw output: {raw[:200]!r}",
        user_message="The router model returned an unexpected response.",
    )


def _parse_routing_plan(raw: str, max_splits: int) -> RoutingPlan:
    """Parse and validate the router JSON into a RoutingPlan."""
    json_str = _extract_json(raw)
    try:
        data: dict[str, Any] = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise SmartError(
            f"Router JSON is malformed: {exc}",
            user_message="The router model returned invalid JSON.",
        ) from exc

    # Validate required fields
    for field_name in ("complexity", "categories_detected", "routing_plan", "reasoning_summary"):
        if field_name not in data:
            raise SmartError(
                f"Router JSON missing required field: {field_name!r}",
                user_message="The router model returned an incomplete routing plan.",
            )

    complexity = str(data["complexity"]).lower()
    if complexity not in ("single", "multi"):
        complexity = "single"

    raw_plan = data["routing_plan"]
    if not isinstance(raw_plan, list) or not raw_plan:
        raise SmartError(
            "Router JSON routing_plan must be a non-empty list.",
            user_message="The router model returned an empty routing plan.",
        )

    # Enforce max_splits limit
    if len(raw_plan) > max_splits:
        raw_plan = raw_plan[:max_splits]

    sub_questions: list[SubQuestion] = []
    for entry in raw_plan:
        if not isinstance(entry, dict):
            continue
        sub_questions.append(
            SubQuestion(
                sub_question=str(entry.get("sub_question", "")),
                category=str(entry.get("category", "general")),
                model_alias=str(entry.get("model_alias", "")),
                context_included=bool(entry.get("context_included", True)),
            )
        )

    if not sub_questions:
        raise SmartError(
            "Router JSON produced no valid sub-questions.",
            user_message="The router model returned no routing entries.",
        )

    categories_detected = [str(c) for c in data.get("categories_detected", [])]

    return RoutingPlan(
        complexity=complexity,
        categories_detected=categories_detected,
        routing_plan=sub_questions,
        reasoning_summary=str(data.get("reasoning_summary", "")),
    )


class RouterModel:
    """Calls the router LLM and returns a RoutingPlan.

    Retries once on schema validation failure before raising SmartError.
    """

    def __init__(
        self,
        registry: SmartRegistry,
        provider_registry: ProviderRegistry,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
        max_splits: int = 5,
    ) -> None:
        self._registry = registry
        self._provider_registry = provider_registry
        self._model_registry = model_registry
        self._key_manager = key_manager
        self._max_splits = max_splits

    async def route(
        self,
        user_message: str,
        history: list[ChatMessage],
        format_hint: str | None,
    ) -> RoutingPlan:
        """Produce a RoutingPlan for the given user message.

        Retries once with an error annotation if the first response fails schema
        validation. Raises SmartError if both attempts fail.
        """
        system_prompt = self._build_system_prompt()
        user_content = user_message
        if format_hint:
            user_content += f"\n\n[Detected output format request: {format_hint}]"

        last_error: str = ""
        for attempt in range(_MAX_RETRIES + 1):
            extra = (
                f"\n\nPrevious attempt failed: {last_error}\nPlease fix the JSON."
                if last_error
                else ""
            )
            raw = await self._call_router(system_prompt, user_content + extra, history)
            try:
                plan = _parse_routing_plan(raw, self._max_splits)
                return plan
            except SmartError as exc:
                last_error = str(exc)
                if attempt >= _MAX_RETRIES:
                    raise

        raise SmartError(
            "Router failed after retries.",
            user_message="Router could not produce a valid plan.",
        )

    def _build_system_prompt(self) -> str:
        return _ROUTER_SYSTEM_PROMPT_TEMPLATE.format(
            max_splits=self._max_splits,
            category_catalogue=_build_category_catalogue(),
            model_assignments=_build_model_assignments(self._registry),
        )

    def _resolve_router_alias(self) -> tuple[str, str]:
        """Return (model_id, provider_name) for the configured router alias."""
        alias_name = self._registry.get_router()
        if alias_name:
            alias_obj = self._model_registry.get(alias_name)
            if alias_obj is not None:
                return alias_obj.model_id, alias_obj.provider

        # Fall back to the first available alias
        all_aliases = self._model_registry.list_all()
        if not all_aliases:
            raise SmartError(
                "No model aliases configured — cannot run the MMAE router.",
                user_message="No models are configured. Add a model alias with /model add.",
            )
        first = all_aliases[0]
        return first.model_id, first.provider

    async def _call_router(
        self,
        system_prompt: str,
        user_content: str,
        history: list[ChatMessage],
    ) -> str:
        model_id, provider_name = self._resolve_router_alias()
        api_key = self._key_manager.get_key(provider_name)
        provider = self._provider_registry.instantiate(provider_name, api_key=api_key)

        # Include a short tail of conversation history for context awareness
        tail = history[-4:] if len(history) > 4 else list(history)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            *tail,
            ChatMessage(role="user", content=user_content),
        ]

        gen_params = GenerationParams(temperature=0.1, max_tokens=1024)
        chunks: list[str] = []
        _t0 = time.monotonic()
        async for chunk in provider.stream_chat(
            messages=messages,
            model=model_id,
            gen_params=gen_params,
        ):
            chunks.append(chunk.text)

        return "".join(chunks)
