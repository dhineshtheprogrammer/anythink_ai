"""FormatterModel — optional post-combiner formatting stage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anythink.providers.base import ChatMessage, GenerationParams

if TYPE_CHECKING:
    from anythink.config.models import ModelRegistry
    from anythink.keys.manager import KeyManager
    from anythink.providers.registry import ProviderRegistry
    from anythink.smart.registry import SmartRegistry

_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "markdown": (
        "Reformat the following response as clean Markdown with appropriate headings, "
        "bold, italics, code blocks, and lists. Preserve all content."
    ),
    "list": (
        "Convert the following response into a clean numbered or bullet list. "
        "Use sub-lists where appropriate. Preserve all information."
    ),
    "table": (
        "Convert the following response into one or more pipe-delimited Markdown tables. "
        "If the content is not tabular, produce the best table representation possible."
    ),
    "code_only": (
        "Extract only the code blocks from the following response. "
        "Remove all prose explanation. Keep only runnable code."
    ),
    "json": (
        "Convert the following response into a valid JSON object or array. "
        "Use descriptive keys. Ensure the output is parseable JSON."
    ),
    "summary": (
        "Condense the following response into a 2–4 sentence executive summary. "
        "Keep only the most important points."
    ),
    "detailed": (
        "Expand the following response with additional depth, concrete examples, "
        "and step-by-step explanations. Be thorough and educational."
    ),
}


class FormatterModel:
    """Applies a requested format to the combiner's output.

    Runs only when the user explicitly requested a format in their message or
    has set a session-level format default via /smart format.
    """

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

    async def format(
        self,
        combined_text: str,
        format_name: str,
    ) -> str:
        """Apply format_name to combined_text. Returns formatted text."""
        instruction = _FORMAT_INSTRUCTIONS.get(format_name)
        if not instruction:
            return combined_text  # unknown format — pass through unchanged

        prompt = self._build_formatter_prompt(combined_text, instruction)
        return await self._call_formatter(prompt)

    def _build_formatter_prompt(self, combined_text: str, instruction: str) -> str:
        return f"{instruction}\n\n## Response to Format\n\n{combined_text}\n\n## Formatted Output\n"

    def _resolve_formatter_alias(self) -> tuple[str, str]:
        # formatter → combiner → first available, in fallback order
        for getter in (self._registry.get_formatter, self._registry.get_combiner):
            alias_name = getter()
            if alias_name:
                alias_obj = self._model_registry.get(alias_name)
                if alias_obj is not None:
                    return alias_obj.model_id, alias_obj.provider

        all_aliases = self._model_registry.list_all()
        if not all_aliases:
            raise RuntimeError("No model aliases configured for formatter.")
        first = all_aliases[0]
        return first.model_id, first.provider

    async def _call_formatter(self, prompt: str) -> str:
        model_id, provider_name = self._resolve_formatter_alias()
        api_key = self._key_manager.get_key(provider_name)
        provider = self._provider_registry.instantiate(provider_name, api_key=api_key)
        gen_params = GenerationParams(temperature=0.2, max_tokens=4096)

        messages = [ChatMessage(role="user", content=prompt)]
        chunks: list[str] = []
        async for chunk in provider.stream_chat(
            messages=messages,
            model=model_id,
            gen_params=gen_params,
        ):
            chunks.append(chunk.text)
        return "".join(chunks)
