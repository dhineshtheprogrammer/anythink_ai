"""Tests for optimize/classifier.py — IntentClassifier."""

from __future__ import annotations

from anythink.optimize.classifier import IntentClassifier


class TestIntentClassifier:
    def setup_method(self) -> None:
        self.clf = IntentClassifier()

    # ── Category classification ───────────────────────────────────────────

    def test_coding_query(self) -> None:
        intent = self.clf.classify("How do I write a Python function to sort a list?")
        assert intent.category == "Coding"
        assert intent.from_user is False

    def test_creative_query(self) -> None:
        intent = self.clf.classify("Write a poem about the ocean at night")
        assert intent.category == "Creative"

    def test_factual_query(self) -> None:
        intent = self.clf.classify("What is the capital of France?")
        assert intent.category == "Factual"

    def test_reasoning_query(self) -> None:
        intent = self.clf.classify("Compare React vs Vue for building enterprise applications")
        assert intent.category == "Reasoning"

    def test_research_query(self) -> None:
        intent = self.clf.classify("Give me a comprehensive overview of machine learning architectures")
        assert intent.category == "Research"

    def test_math_query(self) -> None:
        intent = self.clf.classify("Solve this differential equation and show the proof")
        assert intent.category == "Math"

    def test_unrecognised_query_is_other(self) -> None:
        intent = self.clf.classify("hello there")
        assert intent.category == "Other"

    # ── Format detection ─────────────────────────────────────────────────

    def test_step_by_step_format(self) -> None:
        intent = self.clf.classify("Walk me through how to deploy a Docker container")
        assert intent.format_preference == "step_by_step"

    def test_bullet_format(self) -> None:
        intent = self.clf.classify("List the top 5 benefits of using TypeScript")
        assert intent.format_preference == "bullet"

    def test_concise_format(self) -> None:
        intent = self.clf.classify("Give a quick summary of what an API is")
        assert intent.format_preference == "concise"

    def test_code_only_format(self) -> None:
        intent = self.clf.classify("Just the code for a binary search implementation")
        assert intent.format_preference == "code_only"

    def test_default_format_is_detailed(self) -> None:
        intent = self.clf.classify("Explain how neural networks learn")
        assert intent.format_preference == "detailed"

    # ── Token estimation ──────────────────────────────────────────────────

    def test_estimate_tokens_proportional_to_length(self) -> None:
        short = self.clf.estimate_tokens("hello")
        long = self.clf.estimate_tokens("hello " * 100)
        assert long > short

    def test_estimate_tokens_minimum_one(self) -> None:
        assert self.clf.estimate_tokens("") >= 1

    def test_estimate_tokens_approx_four_chars(self) -> None:
        text = "a" * 400
        estimate = self.clf.estimate_tokens(text)
        assert 90 <= estimate <= 110  # ~100 tokens expected

    # ── Plan mode triggering ──────────────────────────────────────────────

    def test_plan_mode_triggered_by_phrase(self) -> None:
        assert self.clf.should_trigger_plan_mode(
            "Give me a detailed architecture for building a React app",
            token_estimate=50,
            model_context=8192,
        )

    def test_plan_mode_not_triggered_short_simple(self) -> None:
        assert not self.clf.should_trigger_plan_mode(
            "What is Python?",
            token_estimate=4,
            model_context=8192,
        )

    def test_plan_mode_triggered_by_token_ratio(self) -> None:
        # 5000 tokens > 60% of 8000 context window and > 300 threshold
        assert self.clf.should_trigger_plan_mode(
            "X" * (5000 * 4),  # ~5000 tokens
            token_estimate=5000,
            model_context=8000,
        )

    def test_plan_mode_not_triggered_small_fraction_of_context(self) -> None:
        assert not self.clf.should_trigger_plan_mode(
            "Explain what a hash table is",
            token_estimate=10,
            model_context=128000,
        )

    # ── Override flag extraction ──────────────────────────────────────────

    def test_extract_model_flag(self) -> None:
        clean, flags = self.clf.extract_override_flags(
            "How do I sort a list in Python? --model ollama/deepseek-coder"
        )
        assert flags.get("model") == "ollama/deepseek-coder"
        assert "--model" not in clean

    def test_extract_strategy_flag(self) -> None:
        _, flags = self.clf.extract_override_flags(
            "Compare React and Vue --strategy ensemble"
        )
        assert flags.get("strategy") == "ensemble"

    def test_extract_speed_flag(self) -> None:
        _, flags = self.clf.extract_override_flags("Quick answer please --speed")
        assert flags.get("priority") == "speed"

    def test_extract_quality_flag(self) -> None:
        _, flags = self.clf.extract_override_flags("Best possible answer --quality")
        assert flags.get("priority") == "quality"

    def test_extract_no_plan_flag(self) -> None:
        _, flags = self.clf.extract_override_flags("Write a REST API --no-plan")
        assert flags.get("no_plan") == "true"

    def test_no_flags_returns_original_text(self) -> None:
        clean, flags = self.clf.extract_override_flags("Just a plain question")
        assert clean == "Just a plain question"
        assert flags == {}

    def test_multiple_flags_extracted(self) -> None:
        _, flags = self.clf.extract_override_flags(
            "Build an API --model groq/llama3-70b-8192 --speed"
        )
        assert flags.get("model") == "groq/llama3-70b-8192"
        assert flags.get("priority") == "speed"
