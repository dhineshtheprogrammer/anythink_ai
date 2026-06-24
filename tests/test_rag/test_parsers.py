"""Tests for the RAG document parsers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from anythink.rag.parsers import (
    dispatch_parser,
    parse_code_generic,
    parse_csv,
    parse_json,
    parse_markdown,
    parse_python,
    parse_text,
    parse_yaml_file,
)


# ── parse_text ────────────────────────────────────────────────────────────────


class TestParseText:
    def test_returns_single_unit(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.txt"
        f.write_text("Hello world.\n\nSecond paragraph.", encoding="utf-8")
        units = parse_text(f)
        assert len(units) == 1
        text, meta = units[0]
        assert "Hello world" in text
        assert meta["source_path"] == str(f)
        assert meta["start_line"] == 1

    def test_metadata_includes_file_type(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.rst"
        f.write_text("Title\n=====\nContent.", encoding="utf-8")
        _, meta = parse_text(f)[0]
        assert meta["file_type"] == ".rst"

    def test_preprocess_collapses_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("A\n\n\n\n\nB", encoding="utf-8")
        text, _ = parse_text(f)[0]
        assert "\n\n\n" not in text

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        from anythink.exceptions import RAGError

        with pytest.raises(RAGError):
            parse_text(tmp_path / "nonexistent.txt")


# ── parse_markdown ────────────────────────────────────────────────────────────


class TestParseMarkdown:
    def test_splits_at_headings(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "# Title\nIntro text.\n## Section A\nContent A.\n## Section B\nContent B.",
            encoding="utf-8",
        )
        units = parse_markdown(f)
        assert len(units) >= 2

    def test_heading_path_in_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text(
            "# Guide\nIntro.\n## Setup\nInstall steps.\n### Linux\nLinux specific.",
            encoding="utf-8",
        )
        units = parse_markdown(f)
        heading_paths = [meta["heading_path"] for _, meta in units]
        assert any("Setup" in hp for hp in heading_paths)
        assert any("Linux" in hp for hp in heading_paths)

    def test_nested_heading_path_format(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Parent\n## Child\n### Grandchild\nText.", encoding="utf-8")
        units = parse_markdown(f)
        # Find the deepest section
        paths = [meta["heading_path"] for _, meta in units if meta["heading_path"]]
        assert any(" > " in p for p in paths)

    def test_no_headings_falls_back_to_full_text(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("Just plain text, no headings.", encoding="utf-8")
        units = parse_markdown(f)
        assert len(units) == 1
        assert "Just plain text" in units[0][0]

    def test_start_line_is_set(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# H1\nA.\n## H2\nB.", encoding="utf-8")
        units = parse_markdown(f)
        for _, meta in units:
            assert "start_line" in meta
            assert meta["start_line"] >= 1


# ── parse_python ──────────────────────────────────────────────────────────────


class TestParsePython:
    def test_extracts_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text(
            "import os\n\ndef foo():\n    pass\n\ndef bar(x):\n    return x\n",
            encoding="utf-8",
        )
        units = parse_python(f)
        names = [meta.get("function_name", "") for _, meta in units]
        assert "foo" in names
        assert "bar" in names

    def test_extracts_classes(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("class MyClass:\n    def method(self):\n        pass\n", encoding="utf-8")
        units = parse_python(f)
        names = [meta.get("function_name", "") for _, meta in units]
        assert "MyClass" in names

    def test_preamble_unit_has_empty_function_name(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("import sys\nimport os\n\ndef main():\n    pass\n", encoding="utf-8")
        units = parse_python(f)
        preamble = [u for u in units if u[1].get("function_name") == ""]
        assert preamble  # preamble (imports) captured

    def test_fallback_for_syntax_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.py"
        f.write_text("def foo(:\n    pass\n", encoding="utf-8")
        # Should not raise; falls back to plain text
        units = parse_python(f)
        assert len(units) >= 1

    def test_line_numbers_in_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        f.write_text("def a():\n    pass\n\ndef b():\n    pass\n", encoding="utf-8")
        units = parse_python(f)
        for _, meta in units:
            if meta.get("function_name"):
                assert "start_line" in meta
                assert "end_line" in meta


# ── parse_code_generic ────────────────────────────────────────────────────────


class TestParseCodeGeneric:
    def test_go_splits_at_func(self, tmp_path: Path) -> None:
        f = tmp_path / "main.go"
        f.write_text(
            "package main\n\nfunc hello() {\n    fmt.Println(\"hi\")\n}\n\n"
            "func main() {\n    hello()\n}\n",
            encoding="utf-8",
        )
        units = parse_code_generic(f)
        assert len(units) >= 2

    def test_rust_splits_at_fn(self, tmp_path: Path) -> None:
        f = tmp_path / "lib.rs"
        f.write_text(
            "fn foo() -> i32 {\n    42\n}\n\npub fn bar() {\n    foo();\n}\n",
            encoding="utf-8",
        )
        units = parse_code_generic(f)
        assert len(units) >= 1

    def test_metadata_has_source_path(self, tmp_path: Path) -> None:
        f = tmp_path / "code.java"
        f.write_text("public class Foo {\n    public void run() {}\n}\n", encoding="utf-8")
        units = parse_code_generic(f)
        for _, meta in units:
            assert meta["source_path"] == str(f)


# ── parse_csv ─────────────────────────────────────────────────────────────────


class TestParseCSV:
    def test_batches_rows(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        rows = ["name,age"] + [f"user{i},{i}" for i in range(50)]
        f.write_text("\n".join(rows), encoding="utf-8")
        units = parse_csv(f)
        assert len(units) >= 2  # 50 rows / 20 per batch = 3 units

    def test_column_headers_in_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("id,name,score\n1,Alice,95\n2,Bob,87\n", encoding="utf-8")
        units = parse_csv(f)
        assert units
        assert "column_headers" in units[0][1]
        assert "name" in units[0][1]["column_headers"]

    def test_content_includes_values(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("city,pop\nBerlin,3.6M\nParis,2.1M\n", encoding="utf-8")
        text, _ = parse_csv(f)[0]
        assert "Berlin" in text


# ── parse_json ────────────────────────────────────────────────────────────────


class TestParseJSON:
    def test_dict_top_keys_as_units(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        data = {"alpha": {"a": 1}, "beta": {"b": 2}, "gamma": {"c": 3}}
        f.write_text(json.dumps(data), encoding="utf-8")
        units = parse_json(f)
        key_paths = [meta["key_path"] for _, meta in units]
        assert "alpha" in key_paths
        assert "beta" in key_paths

    def test_list_batched(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        data = list(range(25))
        f.write_text(json.dumps(data), encoding="utf-8")
        units = parse_json(f)
        assert len(units) == 3  # 25 items / 10 per batch

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        from anythink.exceptions import RAGError

        f = tmp_path / "bad.json"
        f.write_text("{not: valid json}", encoding="utf-8")
        with pytest.raises(RAGError):
            parse_json(f)


# ── parse_yaml_file ───────────────────────────────────────────────────────────


class TestParseYAML:
    def test_dict_top_keys_as_units(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        data = {"database": {"host": "localhost"}, "cache": {"ttl": 300}}
        f.write_text(yaml.dump(data), encoding="utf-8")
        units = parse_yaml_file(f)
        key_paths = [meta["key_path"] for _, meta in units]
        assert "database" in key_paths
        assert "cache" in key_paths

    def test_empty_file_falls_back(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        # Should not raise; falls back to plain text
        units = parse_yaml_file(f)
        assert isinstance(units, list)


# ── dispatch_parser ───────────────────────────────────────────────────────────


class TestDispatchParser:
    def test_dispatches_py_to_python_parser(self, tmp_path: Path) -> None:
        f = tmp_path / "module.py"
        f.write_text("def hello():\n    pass\n", encoding="utf-8")
        units = dispatch_parser(f)
        assert units
        # Python parser adds function_name metadata
        assert any("function_name" in meta for _, meta in units)

    def test_dispatches_md_to_markdown_parser(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Title\nContent.\n## Section\nMore.", encoding="utf-8")
        units = dispatch_parser(f)
        assert any("heading_path" in meta for _, meta in units)

    def test_dispatches_json_to_json_parser(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        units = dispatch_parser(f)
        assert any(meta.get("key_path") == "key" for _, meta in units)

    def test_unknown_extension_defaults_to_text(self, tmp_path: Path) -> None:
        f = tmp_path / "file.xyz"
        f.write_text("Some content.", encoding="utf-8")
        units = dispatch_parser(f)
        assert len(units) == 1
        assert "Some content" in units[0][0]

    def test_all_units_have_source_path(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("Hello.", encoding="utf-8")
        for _, meta in dispatch_parser(f):
            assert "source_path" in meta
            assert meta["source_path"] == str(f)
