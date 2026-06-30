"""CombinerModel — merges specialist responses into one unified answer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage, GenerationParams
from anythink.smart.store import TemporaryResponseStore

if TYPE_CHECKING:
    from anythink.config.models import ModelRegistry
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.smart.registry import SmartRegistry

_STITCH_INSTRUCTION = """\
Combine the specialist responses into one clean, unified answer.
Keep each specialist's content in the order provided.
Add minimal transitional text between sections where needed.
Do NOT add new information from your own knowledge.
Do NOT reveal which models produced which parts.
"""

_MERGE_INSTRUCTION = """\
Read all specialist responses holistically and produce a single flowing answer
that integrates the information naturally.
You may reorder content, merge related points, and write connecting prose.
The result should read as one unified response — not as joined sections.
Do NOT add new information from your own knowledge.
Do NOT reveal which models produced which parts.
"""


def _format_store_entry(idx: int, entry: object) -> str:
    from anythink.smart.models import SpecialistResponse

    assert isinstance(entry, SpecialistResponse)
    confidence = " ⚠ low confidence" if entry.low_confidence else ""
    return (
        f"[Specialist {idx} — {entry.category} — {entry.model_alias} "
        f"(score: {entry.quality_score}){confidence}]\n"
        f"{entry.response}"
    )


class CombinerModel:
    """Calls the combiner LLM in Stitch or Intelligent Merge mode."""

    def __init__(
        self,
        registry: SmartRegistry,
        provider_registry: ProviderRegistry,
        model_registry: ModelRegistry,
        key_manager: KeyManager,
    ) -> None:
        self._registry = registry
        self._provider_registry = provider_registry
        self._model_registry = model_registry
        self._key_manager = key_manager

    async def combine(
        self,
        store: TemporaryResponseStore,
        mode: str,
    ) -> str:
        """Combine specialist responses.  mode is "stitch" or "merge"."""
        entries = store.all()
        if not entries:
            return ""
        if len(entries) == 1:
            # Single-model passthrough — no combining needed
            return entries[0].response

        prompt = self._build_combiner_prompt(store, mode)
        return await self._call_combiner(prompt)

    def _build_combiner_prompt(self, store: TemporaryResponseStore, mode: str) -> str:
        mode_instruction = _MERGE_INSTRUCTION if mode == "merge" else _STITCH_INSTRUCTION
        formatted_entries = "\n\n".join(
            _format_store_entry(i, e) for i, e in enumerate(store.all(), start=1)
        )
        return (
            f"{mode_instruction}\n\n"
            f"## Specialist Responses\n\n{formatted_entries}\n\n"
            f"## Your Combined Answer\n"
        )

    def _resolve_combiner_alias(self) -> tuple[str, str]:
        alias_name = self._registry.get_combiner()
        if alias_name:
            alias_obj = self._model_registry.get(alias_name)
            if alias_obj is not None:
                return alias_obj.model_id, alias_obj.provider

        all_aliases = self._model_registry.list_all()
        if not all_aliases:
            raise RuntimeError("No model aliases configured for combiner.")
        first = all_aliases[0]
        return first.model_id, first.provider

    def combiner_alias_name(self) -> str:
        """Return the display name of the combiner alias."""
        alias_name = self._registry.get_combiner()
        if alias_name:
            alias_obj = self._model_registry.get(alias_name)
            if alias_obj is not None:
                return alias_name
        all_aliases = self._model_registry.list_all()
        return all_aliases[0].alias if all_aliases else "unknown"

    async def _call_combiner(self, prompt: str) -> str:
        model_id, provider_name = self._resolve_combiner_alias()
        api_key = self._key_manager.get_key(provider_name)
        provider = self._provider_registry.instantiate(provider_name, api_key=api_key)
        gen_params = GenerationParams(temperature=0.4, max_tokens=4096)

        messages = [ChatMessage(role="user", content=prompt)]
        chunks: list[str] = []
        async for chunk in provider.stream_chat(
            messages=messages,
            model=model_id,
            gen_params=gen_params,
        ):
            chunks.append(chunk.text)
        return "".join(chunks)
