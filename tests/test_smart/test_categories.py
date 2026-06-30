"""Tests for smart/categories.py."""

from anythink.smart.categories import (
    CATEGORIES,
    SPECIALIST_CATEGORIES,
    TAG_TO_CATEGORY,
    Category,
)


def test_all_nine_categories_present():
    expected = {
        "math",
        "code",
        "writing",
        "reasoning",
        "research",
        "data",
        "translation",
        "summarization",
        "general",
    }
    assert set(CATEGORIES.keys()) == expected


def test_category_is_frozen_dataclass():
    cat = CATEGORIES["math"]
    assert isinstance(cat, Category)
    try:
        cat.key = "other"  # type: ignore[misc]
        assert False, "Should have raised"
    except (AttributeError, TypeError):
        pass


def test_category_keys_match_dict_keys():
    for key, cat in CATEGORIES.items():
        assert cat.key == key


def test_each_category_has_name_and_description():
    for cat in CATEGORIES.values():
        assert cat.name
        assert cat.description


def test_general_category_present():
    assert "general" in CATEGORIES
    assert "fallback" in CATEGORIES["general"].description.lower()


def test_specialist_categories_excludes_general():
    assert "general" not in SPECIALIST_CATEGORIES
    assert SPECIALIST_CATEGORIES == set(CATEGORIES.keys()) - {"general"}


def test_tag_to_category_all_values_valid():
    for tag, cat in TAG_TO_CATEGORY.items():
        assert cat in CATEGORIES, f"Tag {tag!r} maps to unknown category {cat!r}"


def test_tag_to_category_covers_code_and_math():
    assert TAG_TO_CATEGORY.get("code") == "code"
    assert TAG_TO_CATEGORY.get("math") == "math"


def test_tag_to_category_fallback_to_general():
    assert TAG_TO_CATEGORY.get("general") == "general"
    assert TAG_TO_CATEGORY.get("conversational") == "general"
