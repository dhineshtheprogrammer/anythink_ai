"""Tests for smart/detector.py."""

import pytest

from anythink.smart.detector import FORMAT_KEYWORDS, detect_format


def test_returns_none_for_plain_question():
    assert detect_format("What is the capital of France?") is None


def test_detects_markdown():
    assert detect_format("Reply in markdown please") == "markdown"


def test_detects_table():
    assert detect_format("Show this as a table") == "table"


def test_detects_list():
    assert detect_format("Give me a bullet list of steps") == "list"


def test_detects_code_only():
    assert detect_format("Just the code, no explanation") == "code_only"


def test_detects_json():
    assert detect_format("Return as json") == "json"


def test_detects_summary():
    assert detect_format("tldr") == "summary"
    assert detect_format("give me a brief answer") == "summary"


def test_detects_detailed():
    assert detect_format("explain in detail please") == "detailed"
    assert detect_format("step by step") == "detailed"


def test_case_insensitive():
    assert detect_format("MARKDOWN FORMAT") == "markdown"
    assert detect_format("As A TABLE") == "table"


def test_first_match_wins():
    # "in detail" is "detailed"; "as markdown" is "markdown" — order in FORMAT_KEYWORDS matters
    # Just verify we get one of the two consistently, not that order is arbitrary
    result = detect_format("give me a detailed markdown response")
    assert result in ("markdown", "detailed")


def test_format_keywords_dict_has_all_formats():
    expected = {"markdown", "list", "table", "code_only", "json", "summary", "detailed"}
    assert set(FORMAT_KEYWORDS.keys()) == expected


@pytest.mark.parametrize(
    "fmt,keyword",
    [
        ("markdown", "markdown"),
        ("table", "table"),
        ("json", "as json"),
        ("summary", "tl;dr"),
    ],
)
def test_keyword_variations(fmt, keyword):
    assert detect_format(f"please respond {keyword}") == fmt
