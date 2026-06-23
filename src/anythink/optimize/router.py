"""Routing engine — deterministic model selection with optional meta-LLM fallback."""

from __future__ import annotations

from anythink.optimize.classifier import IntentClassifier
from anythink.optimize.models import OptimizeSettings, QueryIntent, RoutingDecision
from anythink.optimize.rate_limit import RateLimitManager
from anythink.optimize.registry import ModelCapabilityRegistry
from anythink.optimize.rules import RoutingRulesLoader

# ── Scoring constants ─────────────────────────────────────────────────────────

_STRENGTH_MATCH_SCORE = 3.0
_QUALITY_HIGH_SCORE = 2.0
_QUALITY_MED_SCORE = 1.0
_SPEED_FAST_SCORE = 2.0
_SPEED_MED_SCORE = 1.0
_CONTEXT_FITS_SCORE = 1.5
_CONTEXT_TIGHT_SCORE = -2.0   # context window < 1.5× token estimate
_RATE_LIMIT_PENALTY = -10.0

# Minimum confidence from deterministic pass before meta-LLM is invoked
_LOW_CONFIDENCE_THRESHOLD = 0.5

# Ensemble is triggered for these categories when quality-first
_ENSEMBLE_CATEGORIES = frozenset({"Reasoning", "Research", "Creative"})

# Default chain roles
_CHAIN_ROLES = ("draft", "critique", "refine")


class RoutingEngine:
    """Selects model(s) and mixing strategy for a given query.

    Decision order:
    1. User override flags (--model, --strategy, etc.)
    2. User-defined YAML routing rules
    3. Deterministic scoring
    4. Meta-LLM fallback (if low confidence and mode permits) — stubbed for V4.0
    """

    def __init__(
        self,
        registry: ModelCapabilityRegistry,
        rate_limit_manager: RateLimitManager,
        settings: OptimizeSettings,
        rules_loader: RoutingRulesLoader,
        classifier: IntentClassifier,
    ) -> None:
        self._registry = registry
        self._rate = rate_limit_manager
        self._settings = settings
        self._rules = rules_loader
        self._classifier = classifier

    # ── Public API ────────────────────────────────────────────────────────

    def decide(
        self,
        query: str,
        intent: QueryIntent,
        history_token_estimate: int,
        override_flags: dict[str, str],
        mode: str,
    ) -> RoutingDecision:
        """Return a RoutingDecision for *query* given *intent* and constraints."""
        total_tokens = history_token_estimate + self._classifier.estimate_tokens(query)

        # 1. Override flags take precedence
        if override_flags:
            decision = self._apply_overrides(intent, override_flags, total_tokens, mode)
            if decision is not None:
                return decision

        # 2. YAML routing rules
        rule_context = {
            "category": intent.category,
            "tokens": total_tokens,
            "mode": mode,
            "priority": self._settings.priority,
        }
        matched_rule = self._rules.evaluate(rule_context)
        if matched_rule is not None:
            decision = self._apply_rule(matched_rule, intent, total_tokens, mode)
            if decision is not None:
                return decision

        # 3. Deterministic scoring
        decision, confidence = self._deterministic_decide(intent, total_tokens, mode)

        # 4. Meta-LLM stub: if confidence is too low and mode allows, we'd call
        #    an orchestrator model — currently returns the deterministic result
        #    with a confidence flag so the TUI can log it.
        low_conf = confidence < _LOW_CONFIDENCE_THRESHOLD
        if low_conf and self._settings.orchestration_mode != "deterministic":
            decision = RoutingDecision(
                strategy=decision.strategy,
                primary_model=decision.primary_model,
                phase_models=decision.phase_models,
                recombination_model=decision.recombination_model,
                plan_mode=decision.plan_mode,
                confidence=confidence,
                reason=f"{decision.reason} [meta-LLM pending]",
            )

        return decision

    def detect_override_conflict(
        self,
        override: dict[str, str],
        decision: RoutingDecision,
        query_token_estimate: int,
    ) -> str | None:
        """Return a warning string if the override conflicts with constraints, else None."""
        forced_model = override.get("model")
        if not forced_model:
            return None

        cap = self._registry.get(forced_model)
        if cap is None:
            return f"Model '{forced_model}' is not in the capability registry."

        if query_token_estimate > cap.context_window:
            return (
                f"'{forced_model}' has a {cap.context_window:,}-token context window, "
                f"but the query + history is ~{query_token_estimate:,} tokens. "
                f"The response may be truncated."
            )

        if cap.tier == "local" and decision.strategy in ("ensemble", "chaining"):
            return (
                f"Forcing a local model ('{forced_model}') with strategy "
                f"'{decision.strategy}' — other ensemble models may be API-only."
            )

        return None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _apply_overrides(
        self,
        intent: QueryIntent,
        flags: dict[str, str],
        total_tokens: int,
        mode: str,
    ) -> RoutingDecision | None:
        """Build a RoutingDecision from explicit user override flags."""
        strategy = flags.get("strategy", self._settings.mixing_mode)
        forced_model = flags.get("model")
        priority = flags.get("priority", self._settings.priority)
        no_plan = flags.get("no_plan") == "true"

        if forced_model:
            cap = self._registry.get(forced_model)
            if cap is None:
                # Unknown model — fall through to normal routing
                return None
            return RoutingDecision(
                strategy="routing",
                primary_model=forced_model,
                plan_mode=False if no_plan else False,
                confidence=1.0,
                reason=f"User forced model: {forced_model}",
            )

        if strategy != self._settings.mixing_mode:
            primary = self._best_model_for(intent, total_tokens, mode, priority)
            if not primary:
                return None
            ens_models = (
                self._select_ensemble_models(intent, self._settings.ensemble_count, mode)
                if strategy == "ensemble"
                else []
            )
            return RoutingDecision(
                strategy=strategy,
                primary_model=primary,
                phase_models=ens_models,
                plan_mode=False,
                confidence=1.0,
                reason=f"User forced strategy: {strategy}",
            )

        return None

    def _apply_rule(
        self,
        rule: RoutingRulesLoader,  # actually a RoutingRule
        intent: QueryIntent,
        total_tokens: int,
        mode: str,
    ) -> RoutingDecision | None:
        """Translate a YAML RoutingRule action into a RoutingDecision."""
        from anythink.optimize.rules import RoutingRule

        if not isinstance(rule, RoutingRule):
            return None

        action = rule.action
        primary = self._best_model_for(intent, total_tokens, mode, self._settings.priority)
        if not primary:
            return None

        if action.startswith("strategy="):
            strategy = action.split("=", 1)[1].strip()
            rule_ens = (
                self._select_ensemble_models(intent, self._settings.ensemble_count, mode)
                if strategy == "ensemble"
                else []
            )
            return RoutingDecision(
                strategy=strategy,
                primary_model=primary,
                phase_models=rule_ens,
                confidence=0.9,
                reason=f"Matched rule: {rule.name}",
            )
        if action.startswith("model="):
            forced = action.split("=", 1)[1].strip()
            cap = self._registry.get(forced)
            if cap:
                return RoutingDecision(
                    strategy="routing",
                    primary_model=forced,
                    confidence=0.9,
                    reason=f"Matched rule: {rule.name}",
                )
        if action == "plan=true":
            return RoutingDecision(
                strategy="decompose",
                primary_model=primary,
                plan_mode=True,
                confidence=0.9,
                reason=f"Matched rule: {rule.name}",
            )

        return None

    def _deterministic_decide(
        self,
        intent: QueryIntent,
        total_tokens: int,
        mode: str,
    ) -> tuple[RoutingDecision, float]:
        """Score all available models and pick the best strategy."""
        priority = intent.priority_override or self._settings.priority

        # Should plan mode trigger?
        plan_mode = (
            self._settings.plan_mode_enabled
            and intent.category in ("Research",)
        )

        # Select mixing strategy
        if intent.category in _ENSEMBLE_CATEGORIES and priority == "quality" and not plan_mode:
            strategy = "ensemble"
        elif plan_mode:
            strategy = "decompose"
        else:
            strategy = "routing"

        primary = self._best_model_for(intent, total_tokens, mode, priority)
        if primary is None:
            return (
                RoutingDecision(
                    strategy="routing",
                    primary_model="",
                    confidence=0.0,
                    reason="No suitable model found",
                ),
                0.0,
            )

        phase_models: list[str] = []
        recombination: str | None = None

        if strategy == "ensemble":
            phase_models = self._select_ensemble_models(intent, self._settings.ensemble_count, mode)
        elif strategy == "chaining":
            phase_models = self._build_chain(intent, mode)
        elif strategy == "decompose":
            phase_models = self._select_ensemble_models(intent, self._settings.ensemble_count, mode)
            recombination = self._best_local_or_fast(mode)

        # Confidence: high if clear category winner, medium if Other
        confidence = 0.9 if intent.category != "Other" else 0.5

        return (
            RoutingDecision(
                strategy=strategy,
                primary_model=primary,
                phase_models=phase_models,
                recombination_model=recombination,
                plan_mode=plan_mode,
                confidence=confidence,
                reason=f"Deterministic: {intent.category} → {strategy}",
            ),
            confidence,
        )

    def _score_model(
        self,
        model_id: str,
        intent: QueryIntent,
        total_tokens: int,
        priority: str,
    ) -> float:
        cap = self._registry.get(model_id)
        if cap is None:
            return -999.0

        score = 0.0
        lower_cat = intent.category.lower()

        # Strength category match
        if lower_cat in cap.strength_categories:
            score += _STRENGTH_MATCH_SCORE

        # Quality preference
        if priority in ("quality", "hybrid"):
            if cap.quality_class == "high":
                score += _QUALITY_HIGH_SCORE
            elif cap.quality_class == "medium":
                score += _QUALITY_MED_SCORE
        else:
            # Reliability/speed first
            if cap.speed_class == "fast":
                score += _SPEED_FAST_SCORE
            elif cap.speed_class == "medium":
                score += _SPEED_MED_SCORE

        # Context window fit
        if total_tokens < cap.context_window:
            score += _CONTEXT_FITS_SCORE
            if total_tokens > cap.context_window * 0.8:
                score += _CONTEXT_TIGHT_SCORE  # tight fit is risky
        else:
            score += _CONTEXT_TIGHT_SCORE * 2  # won't fit — heavy penalty

        # Rate limit penalty
        if self._rate.is_at_rpm_limit(model_id) or self._rate.is_at_rpd_limit(model_id):
            score += _RATE_LIMIT_PENALTY

        # Unavailability
        window = self._rate._get_window(model_id)
        if window.unavailable:
            score += _RATE_LIMIT_PENALTY * 2

        return score

    def _available_models(self, mode: str) -> list[str]:
        if mode == "online":
            caps = self._registry.available_online()
        elif mode == "offline":
            caps = self._registry.available_offline()
        else:
            caps = self._registry.all()
        return [cap.id for cap in caps]

    def _best_model_for(
        self,
        intent: QueryIntent,
        total_tokens: int,
        mode: str,
        priority: str,
    ) -> str | None:
        candidates = self._available_models(mode)
        if not candidates:
            return None

        scored = [
            (mid, self._score_model(mid, intent, total_tokens, priority))
            for mid in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_id, best_score = scored[0]
        # If the best score is catastrophically negative, no model is usable
        if best_score <= _RATE_LIMIT_PENALTY:
            return None
        return best_id

    def _select_ensemble_models(
        self,
        intent: QueryIntent,
        count: int,
        mode: str,
    ) -> list[str]:
        """Return *count* diverse models for ensemble mode."""
        candidates = self._available_models(mode)
        priority = self._settings.priority

        scored = sorted(
            candidates,
            key=lambda mid: self._score_model(mid, intent, 0, priority),
            reverse=True,
        )

        # Pick top-N, ensuring diversity by preferring different providers
        selected: list[str] = []
        seen_providers: set[str] = set()

        for mid in scored:
            if len(selected) >= count:
                break
            cap = self._registry.get(mid)
            if cap is None:
                continue
            if cap.provider not in seen_providers or len(selected) < count:
                selected.append(mid)
                seen_providers.add(cap.provider)

        # Pad if needed (allow provider duplicates)
        if len(selected) < count:
            for mid in scored:
                if mid not in selected:
                    selected.append(mid)
                if len(selected) >= count:
                    break

        return selected[:count]

    def _build_chain(
        self,
        intent: QueryIntent,
        mode: str,
    ) -> list[str]:
        """Build a draft → critique → refine model chain."""
        candidates = self._available_models(mode)
        if not candidates:
            return []

        # Draft: category-best model
        draft = self._best_model_for(intent, 0, mode, self._settings.priority)

        # Critique: best reasoning model (different from draft if possible)
        reasoning_intent = QueryIntent(
            category="Reasoning",
            format_preference="detailed",
            priority_override=None,
            from_user=False,
        )
        critique_candidates = [m for m in candidates if m != draft]
        if critique_candidates:
            scored = sorted(
                critique_candidates,
                key=lambda mid: self._score_model(mid, reasoning_intent, 0, "quality"),
                reverse=True,
            )
            critique = scored[0]
        else:
            critique = draft

        # Refine: fast local model or same as draft
        refine = self._best_local_or_fast(mode) or draft

        chain = []
        for model in (draft, critique, refine):
            if model:
                chain.append(model)
        return chain

    def _best_local_or_fast(self, mode: str) -> str | None:
        """Return the fastest available local model, or fastest overall."""
        offline_caps = self._registry.available_offline()
        if offline_caps and mode != "online":
            fast_local = [c for c in offline_caps if c.speed_class == "fast"]
            return fast_local[0].id if fast_local else offline_caps[0].id

        online_caps = self._registry.available_online()
        if online_caps:
            fast = [c for c in online_caps if c.speed_class == "fast"]
            return fast[0].id if fast else online_caps[0].id

        return None
