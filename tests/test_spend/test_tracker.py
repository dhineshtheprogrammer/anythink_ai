"""Tests for SpendTracker and pricing estimation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from anythink.providers.base import TokenUsage
from anythink.spend.pricing import estimate_cost
from anythink.spend.tracker import SpendRecord, SpendTracker


class TestEstimateCost:
    def test_known_provider_returns_nonzero(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost("anthropic", "claude-sonnet-4-6", usage)
        assert cost > 0

    def test_local_provider_returns_zero(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        assert estimate_cost("ollama", "llama3", usage) == 0.0
        assert estimate_cost("lm_studio", "any", usage) == 0.0

    def test_unknown_provider_returns_zero(self) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert estimate_cost("nonexistent_provider", "some-model", usage) == 0.0

    def test_openai_gpt4o_has_cost(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost("openai", "gpt-4o", usage)
        assert cost > 0

    def test_groq_returns_zero(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost("groq", "llama3-8b-8192", usage)
        assert cost == 0.0


class TestSpendRecord:
    def test_roundtrip(self) -> None:
        rec = SpendRecord(
            session_id="sess-1",
            model_id="gpt-4o",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0035,
        )
        d = rec.to_dict()
        restored = SpendRecord.from_dict(d)
        assert restored.session_id == rec.session_id
        assert restored.model_id == rec.model_id
        assert restored.cost_usd == rec.cost_usd


class TestSpendTracker:
    def test_empty_session_total_is_zero(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        assert tracker.session_total("missing-session") == 0.0

    def test_record_and_session_total(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        assert tracker.session_total("sess-1") == pytest.approx(0.005)

    def test_multiple_records_accumulate(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.003)
        assert tracker.session_total("sess-1") == pytest.approx(0.008)

    def test_different_sessions_isolated(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        tracker.record("sess-2", "gpt-4o", "openai", usage, cost_usd=0.010)
        assert tracker.session_total("sess-1") == pytest.approx(0.005)
        assert tracker.session_total("sess-2") == pytest.approx(0.010)

    def test_daily_total(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        today_total = tracker.daily_total()
        assert today_total == pytest.approx(0.005)

    def test_monthly_total(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        assert tracker.monthly_total() == pytest.approx(0.005)

    def test_by_model(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)
        tracker.record("sess-1", "gpt-4o-mini", "openai", usage, cost_usd=0.001)
        by_model = tracker.by_model()
        assert "gpt-4o" in by_model
        assert "gpt-4o-mini" in by_model

    def test_by_provider(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.record("s1", "gpt-4o", "openai", usage, cost_usd=0.005)
        tracker.record("s1", "claude-sonnet-4-6", "anthropic", usage, cost_usd=0.010)
        by_prov = tracker.by_provider()
        assert by_prov["openai"] == pytest.approx(0.005)
        assert by_prov["anthropic"] == pytest.approx(0.010)

    def test_persistence_roundtrip(self, xdg_dirs: Paths) -> None:
        tracker1 = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker1.record("sess-1", "gpt-4o", "openai", usage, cost_usd=0.005)

        tracker2 = SpendTracker(xdg_dirs.spend_log_file)
        assert tracker2.session_total("sess-1") == pytest.approx(0.005)

    def test_prune_removes_old_records(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        old_rec = SpendRecord(
            session_id="old-sess",
            model_id="gpt-4o",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.005,
            recorded_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
        tracker._load().append(old_rec)
        tracker._dirty = True
        tracker.save()
        tracker.prune(keep_days=1)
        assert tracker.session_total("old-sess") == 0.0

    def test_no_usage_no_record_needed(self, xdg_dirs: Paths) -> None:
        tracker = SpendTracker(xdg_dirs.spend_log_file)
        assert tracker.all_records() == []
