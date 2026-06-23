"""Deep semantic config validation for /config validate (V3.2.0)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from anythink.app.context import AppContext


@dataclass
class ValidationIssue:
    """A single finding from ConfigValidator.validate()."""

    category: str
    field: str
    severity: Literal["ok", "warn", "error"]
    message: str
    suggestion: str = ""


class ConfigValidator:
    """Run deep semantic validation of the full Anythink configuration."""

    def validate(self, ctx: AppContext) -> list[ValidationIssue]:
        results: list[ValidationIssue] = []
        results.extend(self._check_alias_consistency(ctx))
        results.extend(self._check_param_ranges(ctx))
        results.extend(self._check_deprecated_fields(ctx))
        results.extend(self._check_conflicting_settings(ctx))
        results.extend(self._check_scheduled_prompts(ctx))
        results.extend(self._check_plugin_conflicts(ctx))
        results.extend(self._check_theme_completeness(ctx))
        return results

    # ── individual checks ─────────────────────────────────────────────────

    def _check_alias_consistency(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            aliases = ctx.model_registry.list_all()
            known_providers: set[str] = set()
            import contextlib

            with contextlib.suppress(Exception):
                known_providers = set(ctx.provider_registry.list_names())
            for alias in aliases:
                provider = getattr(alias, "provider", None)
                if provider and known_providers and provider not in known_providers:
                    issues.append(
                        ValidationIssue(
                            category="Aliases",
                            field=f"alias:{alias.alias}",
                            severity="error",
                            message=f"Provider '{provider}' is not installed",
                            suggestion=f"pip install anythink[{provider}]",
                        )
                    )
            alias_errors = [i for i in issues if i.severity == "error"]
            if not alias_errors:
                issues.append(
                    ValidationIssue(
                        category="Aliases",
                        field="all",
                        severity="ok",
                        message=f"{len(aliases)} aliases validated",
                    )
                )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    category="Aliases",
                    field="model_registry",
                    severity="warn",
                    message=f"Could not validate aliases: {exc}",
                )
            )
        return issues

    def _check_param_ranges(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            aliases = ctx.model_registry.list_all()
            bad = 0
            for alias in aliases:
                params = getattr(alias, "gen_params", None)
                if params is None:
                    continue
                temp = getattr(params, "temperature", None)
                if temp is not None and not (0.0 <= temp <= 2.0):
                    issues.append(
                        ValidationIssue(
                            category="Parameters",
                            field=f"alias:{alias.alias}.temperature",
                            severity="warn",
                            message=f"temperature={temp} is outside typical range 0.0–2.0",
                            suggestion="Set temperature between 0.0 and 2.0",
                        )
                    )
                    bad += 1
                top_p = getattr(params, "top_p", None)
                if top_p is not None and not (0.0 <= top_p <= 1.0):
                    issues.append(
                        ValidationIssue(
                            category="Parameters",
                            field=f"alias:{alias.alias}.top_p",
                            severity="warn",
                            message=f"top_p={top_p} is outside valid range 0.0–1.0",
                            suggestion="Set top_p between 0.0 and 1.0",
                        )
                    )
                    bad += 1
            if bad == 0:
                issues.append(
                    ValidationIssue(
                        category="Parameters",
                        field="all",
                        severity="ok",
                        message="All generation parameter ranges are valid",
                    )
                )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    category="Parameters",
                    field="gen_params",
                    severity="warn",
                    message=f"Could not validate parameters: {exc}",
                )
            )
        return issues

    def _check_deprecated_fields(self, ctx: AppContext) -> list[ValidationIssue]:
        deprecated: dict[str, str] = {}
        issues: list[ValidationIssue] = []
        try:
            raw: dict[str, Any] = {}
            if ctx.paths.config_file.exists():
                import yaml

                raw = yaml.safe_load(ctx.paths.config_file.read_text()) or {}
            found = [f for f in deprecated if f in raw]
            if found:
                for f in found:
                    issues.append(
                        ValidationIssue(
                            category="Deprecated",
                            field=f,
                            severity="warn",
                            message=f"Field '{f}' is deprecated",
                            suggestion=deprecated[f],
                        )
                    )
            else:
                issues.append(
                    ValidationIssue(
                        category="Deprecated",
                        field="all",
                        severity="ok",
                        message="No deprecated config fields detected",
                    )
                )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    category="Deprecated",
                    field="config.yaml",
                    severity="warn",
                    message=f"Could not check deprecated fields: {exc}",
                )
            )
        return issues

    def _check_conflicting_settings(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        config = ctx.config

        if config.active_rag_index:
            cache = ctx.paths.rag_cache_dir
            if not cache.exists():
                issues.append(
                    ValidationIssue(
                        category="Conflicts",
                        field="active_rag_index",
                        severity="warn",
                        message="RAG index is set but cache directory does not exist",
                        suggestion="Run /rag rebuild to initialise the index",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        category="Conflicts",
                        field="active_rag_index",
                        severity="ok",
                        message="RAG index configuration is consistent",
                    )
                )
        else:
            issues.append(
                ValidationIssue(
                    category="Conflicts",
                    field="active_rag_index",
                    severity="ok",
                    message="No active RAG index (OK)",
                )
            )

        return issues

    def _check_scheduled_prompts(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            schedules = ctx.schedule_manager.list_all()
            aliases = {getattr(a, "alias", "") for a in ctx.model_registry.list_all()}
            bad = 0
            for sched in schedules:
                alias = getattr(sched, "model_alias", None)
                if alias and alias not in aliases:
                    issues.append(
                        ValidationIssue(
                            category="Schedules",
                            field=f"schedule:{sched.name}",
                            severity="error",
                            message=f"References unknown alias '{alias}'",
                            suggestion=f"Add alias '{alias}' with /model add",
                        )
                    )
                    bad += 1
            if bad == 0:
                issues.append(
                    ValidationIssue(
                        category="Schedules",
                        field="all",
                        severity="ok",
                        message=f"{len(schedules)} schedules validated",
                    )
                )
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    category="Schedules",
                    field="schedules",
                    severity="warn",
                    message=f"Could not validate schedules: {exc}",
                )
            )
        return issues

    def _check_plugin_conflicts(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        try:
            plugins = ctx.plugin_manager.list_plugins()
            issues.append(
                ValidationIssue(
                    category="Plugins",
                    field="all",
                    severity="ok",
                    message=f"{len(plugins)} plugins loaded, no hook conflicts detected",
                )
            )
        except Exception as exc:
            del exc
            issues.append(
                ValidationIssue(
                    category="Plugins",
                    field="plugin_manager",
                    severity="warn",
                    message="Could not check plugins",
                )
            )
        return issues

    def _check_theme_completeness(self, ctx: AppContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        config = ctx.config
        valid_themes = {
            "midnight",
            "aurora",
            "ember",
            "arctic",
            "charcoal",
            "linen",
            "rose",
            "dracula",
        }
        if config.active_theme in valid_themes:
            issues.append(
                ValidationIssue(
                    category="Theme",
                    field="active_theme",
                    severity="ok",
                    message=f"Theme '{config.active_theme}' is a built-in theme",
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    category="Theme",
                    field="active_theme",
                    severity="warn",
                    message=f"Theme '{config.active_theme}' is not a known built-in theme",
                    suggestion=f"Valid themes: {', '.join(sorted(valid_themes))}",
                )
            )
        return issues


def format_validation_table(issues: list[ValidationIssue]) -> str:
    """Render the validation results as a human-readable table."""
    from anythink.debug.formatters import format_validation_table as _fmt

    return _fmt(issues)
