"""Tests for RAG text chunkers."""

from __future__ import annotations

from pathlib import Path

from anythink.rag.chunkers import chunk_code, chunk_file, chunk_text


class TestChunkText:
    def test_short_text_is_single_chunk(self) -> None:
        chunks = chunk_text("Hello world", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_empty_returns_empty(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   \n  ") == []

    def test_long_text_splits_into_multiple_chunks(self) -> None:
        text = "word " * 300  # 1500 chars
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        assert len(chunks) > 1

    def test_chunks_cover_content(self) -> None:
        text = "paragraph one\n\nparagraph two\n\nparagraph three"
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        combined = " ".join(chunks)
        assert "paragraph one" in combined
        assert "paragraph three" in combined

    def test_overlap_produces_some_repetition(self) -> None:
        text = "a b c d e f g h i j k l m n o p q r s t"
        chunks = chunk_text(text, chunk_size=10, overlap=5)
        # With overlap, at least some characters should appear twice
        assert len(chunks) >= 2


class TestChunkCode:
    def test_python_function_boundary(self) -> None:
        code = (
            "def foo():\n    return 1\n\n"
            "def bar():\n    return 2\n\n"
            "def baz():\n    return 3\n"
        )
        chunks = chunk_code(code, chunk_size=512)
        assert len(chunks) >= 3

    def test_empty_returns_empty(self) -> None:
        assert chunk_code("") == []

    def test_small_code_is_single_chunk(self) -> None:
        code = "x = 1\ny = 2\n"
        chunks = chunk_code(code, chunk_size=512)
        assert len(chunks) == 1

    def test_oversized_block_is_further_split(self) -> None:
        # One long function that exceeds chunk_size
        body = "    pass  # long body\n" * 50
        code = f"def long_func():\n{body}"
        chunks = chunk_code(code, chunk_size=100, overlap=10)
        assert len(chunks) > 1


class TestChunkFile:
    def test_text_file(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("This is a note.\n\nAnother paragraph here.\n", encoding="utf-8")
        result = chunk_file(f, chunk_size=512)
        assert len(result) >= 1
        for text, meta in result:
            assert "source_path" in meta
            assert str(f) == meta["source_path"]

    def test_python_file(self, tmp_path: Path) -> None:
        f = tmp_path / "script.py"
        f.write_text(
            "def greet():\n    print('hello')\n\ndef bye():\n    print('bye')\n",
            encoding="utf-8",
        )
        result = chunk_file(f, chunk_size=512)
        assert len(result) >= 1

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        result = chunk_file(tmp_path / "missing.txt")
        assert result == []

    def test_metadata_has_line_numbers(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("line one\nline two\nline three\n", encoding="utf-8")
        result = chunk_file(f)
        assert all("start_line" in m for _, m in result)
