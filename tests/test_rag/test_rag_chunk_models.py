"""Tests for rag/models.py (RetrievalResult methods)."""

from __future__ import annotations

from anythink.rag.models import RetrievalResult


def _result(**kwargs) -> RetrievalResult:
    defaults = dict(source_path="src.py", chunk_text="code", relevance=0.8, chunk_index=0)
    defaults.update(kwargs)
    return RetrievalResult(**defaults)


class TestRetrievalResultExcerpt:
    def test_excerpt_short_text_unchanged(self) -> None:
        r = _result(chunk_text="short text")
        assert r.excerpt() == "short text"

    def test_excerpt_truncates_long_text(self) -> None:
        r = _result(chunk_text="x" * 200)
        result = r.excerpt(max_chars=100)
        assert result == "x" * 100 + "…"


class TestRetrievalResultSourceLabel:
    def test_heading_path_included(self) -> None:
        r = _result(heading_path="section/sub")
        assert "section/sub" in r.source_label()

    def test_function_name_included(self) -> None:
        r = _result(function_name="my_func")
        assert "my_func()" in r.source_label()

    def test_line_range_included(self) -> None:
        r = _result(start_line=10, end_line=20)
        assert "L10" in r.source_label()

    def test_page_number_included(self) -> None:
        r = _result(page_number=5)
        assert "p.5" in r.source_label()

    def test_source_only_when_no_extras(self) -> None:
        r = _result()
        assert r.source_label() == "src.py"
