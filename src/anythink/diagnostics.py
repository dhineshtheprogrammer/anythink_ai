"""Health diagnostics for Anythink installations."""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from anythink.app.context import AppContext

_OPTIONAL_DEPS = [
    "groq",
    "openai",
    "anthropic",
    "google.generativeai",
    "mistralai",
    "cohere",
    "sentence_transformers",
    "whisper",
    "playwright",
    "fpdf2",
    "apscheduler",
    "croniter",
]


@dataclass
class DiagResult:
    """One diagnostic check result."""

    category: str
    name: str
    status: Literal["ok", "warn", "fail"]
    message: str
    detail: str = ""


def _check_python() -> list[DiagResult]:
    ver = sys.version_info
    version_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if (ver.major, ver.minor) >= (3, 11):
        return [DiagResult("Python Environment", "Python version", "ok", version_str)]
    return [
        DiagResult(
            "Python Environment",
            "Python version",
            "fail",
            version_str,
            "Anythink requires Python 3.11+. Upgrade your Python installation.",
        )
    ]


def _check_deps() -> list[DiagResult]:
    results = []
    for dep in _OPTIONAL_DEPS:
        spec = importlib.util.find_spec(dep.split(".")[0])
        status: Literal["ok", "warn"] = "ok" if spec is not None else "warn"
        msg = "installed" if spec is not None else "not installed (optional)"
        results.append(DiagResult("Dependencies", dep, status, msg))
    return results


def _check_api_keys(ctx: AppContext) -> list[DiagResult]:
    results = []
    try:
        providers = ctx.key_manager.list_providers()
    except Exception as e:
        return [DiagResult("API Keys", "Key manager", "fail", str(e))]
    if not providers:
        return [DiagResult("API Keys", "API keys", "warn", "No API keys configured")]
    for prov in providers:
        results.append(DiagResult("API Keys", prov, "ok", "configured"))
    return results


async def _check_providers(ctx: AppContext) -> list[DiagResult]:
    results = []
    aliases = ctx.model_registry.list_all()
    seen_providers: set[str] = set()
    for alias in aliases:
        if alias.provider in seen_providers:
            continue
        seen_providers.add(alias.provider)
        try:
            api_key = ctx.key_manager.get_key(alias.provider)
            prov_cls = ctx.provider_registry.get(alias.provider)
            if prov_cls is None:
                results.append(
                    DiagResult(
                        "Providers", alias.provider, "warn", "provider not found in registry"
                    )
                )
                continue
            provider = prov_cls(api_key=api_key)
            reachable = await asyncio.wait_for(provider.test_connection(), timeout=5.0)
            if reachable:
                results.append(DiagResult("Providers", alias.provider, "ok", "reachable"))
            else:
                results.append(
                    DiagResult(
                        "Providers",
                        alias.provider,
                        "fail",
                        "unreachable",
                        f"Run: anythink keys test {alias.provider}",
                    )
                )
        except TimeoutError:
            results.append(DiagResult("Providers", alias.provider, "warn", "timed out (>5s)"))
        except Exception as e:
            results.append(DiagResult("Providers", alias.provider, "warn", str(e)[:80]))
    if not seen_providers:
        results.append(DiagResult("Providers", "No aliases", "warn", "No model aliases configured"))
    return results


def _check_config(ctx: AppContext) -> list[DiagResult]:
    results = []
    files = {
        "config.yaml": ctx.paths.config_file,
        "models.yaml": ctx.paths.models_file,
        "personas.yaml": ctx.paths.personas_file,
        "templates.yaml": ctx.paths.templates_file,
        "schedules.yaml": ctx.paths.schedules_file,
    }
    for name, path in files.items():
        if not path.exists():
            results.append(
                DiagResult("Config Files", name, "ok", "not present (will be created on first use)")
            )
            continue
        try:
            import yaml

            yaml.safe_load(path.read_text())
            results.append(DiagResult("Config Files", name, "ok", "valid YAML"))
        except Exception as e:
            results.append(DiagResult("Config Files", name, "fail", "invalid YAML", str(e)[:100]))
    return results


def _check_disk(ctx: AppContext) -> list[DiagResult]:
    results = []
    try:
        usage = shutil.disk_usage(ctx.paths.data_dir)
        free_gb = usage.free / (1024**3)
        status: Literal["ok", "warn", "fail"] = "ok"
        if free_gb < 0.1:
            status = "fail"
        elif free_gb < 1.0:
            status = "warn"
        results.append(DiagResult("Disk", "Free space", status, f"{free_gb:.1f} GB free"))
    except Exception as e:
        results.append(DiagResult("Disk", "Free space", "warn", str(e)))
    return results


async def run_diagnostics(ctx: AppContext) -> list[DiagResult]:
    """Run all diagnostic checks and return results grouped by category."""
    results: list[DiagResult] = []
    results += _check_python()
    results += _check_deps()
    results += _check_api_keys(ctx)
    results += await _check_providers(ctx)
    results += _check_config(ctx)
    results += _check_disk(ctx)
    return results
