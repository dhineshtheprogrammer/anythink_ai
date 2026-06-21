"""Static pricing table for estimating LLM API costs.

All rates are per-token (not per-million). Update periodically as providers
change pricing. All figures are estimates; actual billing may differ.
"""

from __future__ import annotations

from anythink.providers.base import TokenUsage

# Format: provider -> model_id_prefix -> {prompt: rate, completion: rate}
# Rates are per single token in USD.
_PRICING: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o": {"prompt": 0.0000025, "completion": 0.00001},
        "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.0000006},
        "gpt-4-turbo": {"prompt": 0.00001, "completion": 0.00003},
        "gpt-3.5-turbo": {"prompt": 0.0000005, "completion": 0.0000015},
    },
    "anthropic": {
        "claude-opus-4-8": {"prompt": 0.000015, "completion": 0.000075},
        "claude-sonnet-4-6": {"prompt": 0.000003, "completion": 0.000015},
        "claude-haiku-4-5": {"prompt": 0.00000025, "completion": 0.00000125},
    },
    "groq": {
        # Groq is currently free for most models
        "llama3-8b": {"prompt": 0.0, "completion": 0.0},
        "llama3-70b": {"prompt": 0.0, "completion": 0.0},
        "llama-3.1": {"prompt": 0.0, "completion": 0.0},
        "mixtral": {"prompt": 0.0, "completion": 0.0},
        "gemma": {"prompt": 0.0, "completion": 0.0},
    },
    "gemini": {
        "gemini-2.0-flash": {"prompt": 0.000000075, "completion": 0.0000003},
        "gemini-1.5-flash": {"prompt": 0.000000075, "completion": 0.0000003},
        "gemini-1.5-pro": {"prompt": 0.00000125, "completion": 0.000005},
    },
    "mistral": {
        "mistral-large": {"prompt": 0.000003, "completion": 0.000009},
        "mistral-small": {"prompt": 0.000001, "completion": 0.000003},
        "open-mixtral": {"prompt": 0.000002, "completion": 0.000006},
        "codestral": {"prompt": 0.000001, "completion": 0.000003},
    },
    "cohere": {
        "command-r-plus": {"prompt": 0.000003, "completion": 0.000015},
        "command-r": {"prompt": 0.0000005, "completion": 0.0000015},
        "command": {"prompt": 0.000001, "completion": 0.000002},
        "command-light": {"prompt": 0.0000003, "completion": 0.0000006},
    },
    # Local providers always $0
    "ollama": {},
    "lm_studio": {},
}


def estimate_cost(provider: str, model_id: str, usage: TokenUsage) -> float:
    """Return estimated USD cost for a single response.

    Matches model_id against known prefixes; falls back to $0.00 for
    unrecognised models or local providers.
    """
    provider_rates = _PRICING.get(provider, {})
    rates: dict[str, float] | None = None

    for prefix, r in provider_rates.items():
        if model_id.startswith(prefix):
            rates = r
            break

    if rates is None:
        return 0.0

    return (usage.prompt_tokens * rates.get("prompt", 0.0)) + (
        usage.completion_tokens * rates.get("completion", 0.0)
    )
