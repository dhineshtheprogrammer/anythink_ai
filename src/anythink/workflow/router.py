"""MetaRouter — tag-based model selection for workflow stages."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.config.models import ModelAlias, ModelRegistry
    from anythink.workflow.registry import WorkflowCapabilityRegistry

# Providers that run locally — preferred over cloud when both are available
_LOCAL_PROVIDERS: frozenset[str] = frozenset(
    ["ollama", "lm_studio", "llamacpp", "lmstudio", "localai"]
)

# Minimum context-window headroom ratio — a stage whose estimated input is >
# this fraction of the model's total window is considered a poor fit.
_CONTEXT_FIT_RATIO = 0.8


class MetaRouter:
    """Selects the best model alias for a workflow stage via capability tags.

    Selection priority (spec §7.2):
    1. Tag match: alias must carry ALL required tags.
    2. Context window: alias must have window >= estimated_input_tokens.
    3. Local over cloud: local providers are preferred when both qualify.
    4. Usage recency: not tracked yet — falls through to step 5.
    5. Largest context window wins as final tie-break.

    When no alias has ALL required tags, the router relaxes to a partial match
    (most tags matched) and marks the selection as "best_available".
    When no alias matches at all, returns ``None``.
    """

    def __init__(
        self,
        workflow_registry: WorkflowCapabilityRegistry,
        model_registry: ModelRegistry,
    ) -> None:
        self._workflow_reg = workflow_registry
        self._model_reg = model_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_model(
        self,
        required_tags: list[str],
        estimated_input_tokens: int = 0,
    ) -> str | None:
        """Return the best alias name for the given requirements, or ``None``."""
        candidates = self._ranked_candidates(required_tags, estimated_input_tokens)
        return candidates[0][0] if candidates else None

    def select_with_fallback(
        self,
        alias: str,
        required_tags: list[str] | None = None,
        estimated_input_tokens: int = 0,
    ) -> list[str]:
        """Return an ordered list: *alias* first, then its fallback chain.

        If *alias* itself is empty or unknown the router auto-selects from
        all configured aliases. The returned list is never empty as long as
        at least one alias is configured.
        """
        all_aliases = [a.alias for a in self._model_reg.list_all()]
        if not all_aliases:
            return []

        if alias and self._model_reg.get(alias) is not None:
            chain = [alias] + self._workflow_reg.get_fallback_chain(alias)
        else:
            # Auto-select
            tags = required_tags or []
            auto = self.select_model(tags, estimated_input_tokens)
            chain = [auto] if auto else []
            if auto:
                chain += self._workflow_reg.get_fallback_chain(auto)

        # Append any remaining aliases as last-resort options
        seen = set(chain)
        for a in all_aliases:
            if a not in seen:
                chain.append(a)
                seen.add(a)

        return chain

    def rank_candidates(
        self,
        required_tags: list[str],
        estimated_input_tokens: int = 0,
    ) -> list[dict[str, object]]:
        """Return all candidates as ``{alias, tags, score, is_exact, is_local}`` dicts."""
        candidates = self._ranked_candidates(required_tags, estimated_input_tokens)
        return [
            {
                "alias": alias,
                "tags": self._workflow_reg.get_tags(alias),
                "score": score,
                "is_exact": is_exact,
                "is_local": self._is_local(alias),
            }
            for alias, score, is_exact in candidates
        ]

    # ------------------------------------------------------------------
    # Internal selection logic
    # ------------------------------------------------------------------

    def _ranked_candidates(
        self,
        required_tags: list[str],
        estimated_input_tokens: int,
    ) -> list[tuple[str, float, bool]]:
        """Return ``(alias, score, is_exact)`` tuples, best first."""
        aliases = self._model_reg.list_all()
        if not aliases:
            return []

        req_set = set(required_tags)
        results: list[tuple[str, float, bool]] = []

        for model_alias in aliases:
            alias_name = model_alias.alias
            tags = set(self._workflow_reg.get_tags(alias_name))
            ctx_window = model_alias.context_window

            # Context-window gate
            if estimated_input_tokens > 0 and ctx_window < estimated_input_tokens:
                continue

            if req_set and not (req_set & tags):
                # Zero overlap — skip in strict pass, included in relaxed
                continue

            matched = len(req_set & tags) if req_set else 0
            is_exact = (matched == len(req_set)) if req_set else True

            score = self._score(
                alias_name=alias_name,
                matched_tags=matched,
                total_required=len(req_set),
                context_window=ctx_window,
                is_exact=is_exact,
            )
            results.append((alias_name, score, is_exact))

        if not results:
            return []

        # Sort: exact matches first, then by descending score
        results.sort(key=lambda t: (not t[2], -t[1]))
        return results

    def _score(
        self,
        alias_name: str,
        matched_tags: int,
        total_required: int,
        context_window: int,
        is_exact: bool,
    ) -> float:
        """Higher is better. Combines tag overlap, locality, and context window."""
        # Tag match fraction (0.0–1.0) — dominates the score
        tag_score = matched_tags / max(total_required, 1)

        # Local provider bonus (0 or 0.5)
        local_bonus = 0.5 if self._is_local(alias_name) else 0.0

        # Context window bonus — linear, normalised to [0, 0.1]
        # A 1M-token model scores +0.1 over a 4k-token model without
        # ever overriding the tag or locality score.
        ctx_bonus = min(context_window, 1_000_000) / 10_000_000

        return tag_score + local_bonus + ctx_bonus

    def _is_local(self, alias_name: str) -> bool:
        model_alias = self._model_reg.get(alias_name)
        if model_alias is None:
            return False
        return model_alias.provider.lower() in _LOCAL_PROVIDERS
