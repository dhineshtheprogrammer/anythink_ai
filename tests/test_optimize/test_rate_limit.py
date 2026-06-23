"""Tests for optimize/rate_limit.py — RateLimitManager."""

from __future__ import annotations

import json
import time

import pytest

from anythink.config.manager import Paths
from anythink.optimize.models import ModelCapability
from anythink.optimize.rate_limit import RateLimitManager, _WINDOW_SECONDS
from anythink.optimize.registry import ModelCapabilityRegistry


def _make_registry_with_models(tmp_path_factory: pytest.TempPathFactory) -> ModelCapabilityRegistry:
    """Create a registry with two test models: one with RPM=3, one local (no limits)."""
    tmp = tmp_path_factory.mktemp("reg")
    models = [
        ModelCapability(
            id="test/limited",
            provider="test",
            display_name="Limited Model",
            tier="free-api",
            context_window=4096,
            max_output_tokens=1024,
            rpm_limit=3,
            tpm_limit=1000,
            rpd_limit=10,
            strength_categories=["coding"],
            speed_class="fast",
            quality_class="medium",
            supports_system_prompt=True,
            supports_streaming=True,
            requires_network=True,
        ),
        ModelCapability(
            id="test/unlimited",
            provider="test-local",
            display_name="Local Model",
            tier="local",
            context_window=32768,
            max_output_tokens=4096,
            rpm_limit=None,
            tpm_limit=None,
            rpd_limit=None,
            strength_categories=["coding"],
            speed_class="medium",
            quality_class="medium",
            supports_system_prompt=True,
            supports_streaming=True,
            requires_network=False,
        ),
    ]
    bundled_path = tmp / "bundled.json"
    bundled_path.write_text(
        json.dumps({"_registry_version": "4.0.0", "models": [m.to_dict() for m in models]})
    )
    return ModelCapabilityRegistry(bundled_path=bundled_path, user_path=tmp / "user.json")


@pytest.fixture()
def registry(tmp_path_factory: pytest.TempPathFactory) -> ModelCapabilityRegistry:
    return _make_registry_with_models(tmp_path_factory)


class TestRateLimitManager:
    def test_record_request_increments_counters(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        mgr.record_request("test/limited", tokens=500)
        mgr.record_request("test/limited", tokens=300)

        window = mgr._get_window("test/limited")
        assert window.requests_in_window == 2
        assert window.tokens_in_window == 800
        assert window.requests_today == 2

    def test_is_at_rpm_limit_false_below_threshold(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        mgr.record_request("test/limited", tokens=100)
        mgr.record_request("test/limited", tokens=100)
        assert mgr.is_at_rpm_limit("test/limited") is False

    def test_is_at_rpm_limit_true_at_threshold(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        for _ in range(3):  # RPM limit = 3
            mgr.record_request("test/limited", tokens=100)
        assert mgr.is_at_rpm_limit("test/limited") is True

    def test_local_model_never_at_rpm_limit(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        for _ in range(100):
            mgr.record_request("test/unlimited", tokens=1000)
        assert mgr.is_at_rpm_limit("test/unlimited") is False

    def test_is_at_tpm_limit(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        mgr.record_request("test/limited", tokens=900)
        # Next request would push to 900 + 200 = 1100 > tpm_limit (1000)
        assert mgr.is_at_tpm_limit("test/limited", estimated_tokens=200) is True
        assert mgr.is_at_tpm_limit("test/limited", estimated_tokens=50) is False

    def test_is_at_rpd_limit(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        for _ in range(10):  # RPD limit = 10
            mgr.record_request("test/limited", tokens=10)
        assert mgr.is_at_rpd_limit("test/limited") is True

    def test_seconds_until_available_positive_when_at_limit(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        secs = mgr.seconds_until_available("test/limited")
        assert secs >= 0.0
        assert secs <= _WINDOW_SECONDS

    def test_find_next_available_skips_exhausted(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        # Exhaust the limited model
        for _ in range(3):
            mgr.record_request("test/limited", tokens=100)

        result = mgr.find_next_available(["test/limited", "test/unlimited"])
        assert result == "test/unlimited"

    def test_find_next_available_returns_none_when_all_exhausted(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        # Exhaust limited and mark unlimited as unavailable
        for _ in range(3):
            mgr.record_request("test/limited", tokens=100)
        mgr.mark_unavailable("test/unlimited")

        result = mgr.find_next_available(["test/limited", "test/unlimited"])
        assert result is None

    def test_mark_unavailable_excludes_model(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        mgr.mark_unavailable("test/limited")

        result = mgr.find_next_available(["test/limited"])
        assert result is None

    def test_reset_counters_clears_all(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        for _ in range(3):
            mgr.record_request("test/limited", tokens=100)
        assert mgr.is_at_rpm_limit("test/limited") is True

        mgr.reset_counters()
        assert mgr.is_at_rpm_limit("test/limited") is False

    def test_save_and_reload_persists_state(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        state_path = xdg_dirs.rate_limit_state_file
        mgr = RateLimitManager(state_path=state_path, registry=registry)
        mgr.record_request("test/limited", tokens=200)
        mgr.save()

        assert state_path.exists()
        raw = json.loads(state_path.read_text())
        assert "windows" in raw

    def test_unknown_model_not_at_limit(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        assert mgr.is_at_rpm_limit("nonexistent/model") is False
        assert mgr.is_at_rpd_limit("nonexistent/model") is False

    def test_get_status_returns_windows_for_all_registry_models(self, xdg_dirs: Paths, registry: ModelCapabilityRegistry) -> None:
        mgr = RateLimitManager(state_path=xdg_dirs.rate_limit_state_file, registry=registry)
        status = mgr.get_status()
        model_ids = {w.model_id for w in status}
        assert "test/limited" in model_ids
        assert "test/unlimited" in model_ids
