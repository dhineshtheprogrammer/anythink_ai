"""Tests for GenerationParams and _resolve_params."""

from __future__ import annotations

from anythink.providers.base import GenerationParams, _resolve_params


class TestGenerationParams:
    def test_defaults(self) -> None:
        p = GenerationParams()
        assert p.temperature == 0.7
        assert p.max_tokens is None
        assert p.top_p is None
        assert p.frequency_penalty is None
        assert p.presence_penalty is None

    def test_custom_values(self) -> None:
        p = GenerationParams(temperature=0.3, max_tokens=512, top_p=0.9)
        assert p.temperature == 0.3
        assert p.max_tokens == 512
        assert p.top_p == 0.9


class TestResolveParams:
    def test_gen_params_wins_over_kwargs(self) -> None:
        p = GenerationParams(temperature=0.1, max_tokens=100)
        resolved = _resolve_params(p, temperature=0.9, max_tokens=9999)
        assert resolved.temperature == 0.1
        assert resolved.max_tokens == 100

    def test_fallback_when_gen_params_none(self) -> None:
        resolved = _resolve_params(None, temperature=0.5, max_tokens=200)
        assert resolved.temperature == 0.5
        assert resolved.max_tokens == 200

    def test_fallback_none_max_tokens(self) -> None:
        resolved = _resolve_params(None, temperature=0.7, max_tokens=None)
        assert resolved.max_tokens is None

    def test_gen_params_identity(self) -> None:
        p = GenerationParams(temperature=0.42)
        resolved = _resolve_params(p, temperature=0.9, max_tokens=None)
        assert resolved is p
