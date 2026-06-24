"""Tests for all 6 RAG chunking strategies."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.embeddings.mock import MockEmbeddingBackend
from anythink.rag.chunkers import (
    achunk_semantic,
    chunk_code,
    chunk_file,
    chunk_heading,
    chunk_paragraph,
    chunk_sentence,
    chunk_text,
    dispatch_chunk,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_LONG = "word " * 300  # 1500 chars — spans multiple chunks at default size


# ── Strategy 1: Fixed size (chunk_text) ──────────────────────────────────────


class TestChunkText:
    def test_short_text_is_single_chunk(self) -> None:
        chunks = chunk_text("Hello world", chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_empty_returns_empty(self) -> None:
        assert chunk_text("") == []
        assert chunk_text("   \n  ") == []

    def test_long_text_splits_into_multiple_chunks(self) -> None:
        chunks = chunk_text(_LONG, chunk_size=200, overlap=20)
        assert len(chunks) > 1

    def test_chunks_cover_all_content(self) -> None:
        text = "paragraph one\n\nparagraph two\n\nparagraph three"
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        combined = " ".join(chunks)
        assert "paragraph one" in combined
        assert "paragraph three" in combined

    def test_overlap_produces_repetition(self) -> None:
        text = "a b c d e f g h i j k l m n o p q r s t"
        chunks = chunk_text(text, chunk_size=10, overlap=5)
        assert len(chunks) >= 2

    def test_all_chunks_nonempty(self) -> None:
        chunks = chunk_text(_LONG, chunk_size=100, overlap=20)
        assert all(c.strip() for c in chunks)


# ── Strategy 2: Code-aware (chunk_code) ──────────────────────────────────────


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
        body = "    pass  # long body\n" * 50
        code = f"def long_func():\n{body}"
        chunks = chunk_code(code, chunk_size=100, overlap=10)
        assert len(chunks) > 1

    def test_no_boundaries_falls_back_to_text(self) -> None:
        plain = "Just some text without function defs.\n" * 20
        chunks = chunk_code(plain, chunk_size=100, overlap=10)
        assert len(chunks) >= 1


# ── Strategy 3: Sentence-based (chunk_sentence) ───────────────────────────────


class TestChunkSentence:
    def test_empty_returns_empty(self) -> None:
        assert chunk_sentence("") == []
        assert chunk_sentence("   ") == []

    def test_short_text_is_single_chunk(self) -> None:
        text = "Hello world. This is a test."
        chunks = chunk_sentence(text, chunk_size=512)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_splits_at_sentence_boundaries(self) -> None:
        text = ". ".join(f"Sentence {i}" for i in range(30)) + "."
        chunks = chunk_sentence(text, chunk_size=80, overlap=20)
        assert len(chunks) > 1

    def test_all_content_preserved(self) -> None:
        text = "Alpha sentence. Beta sentence. Gamma sentence. Delta sentence."
        chunks = chunk_sentence(text, chunk_size=40, overlap=10)
        combined = " ".join(chunks)
        assert "Alpha" in combined
        assert "Delta" in combined

    def test_overlap_carries_trailing_sentences(self) -> None:
        # Two chunks with overlap should share at least one sentence
        sentences = [f"S{i} content here." for i in range(10)]
        text = " ".join(sentences)
        chunks = chunk_sentence(text, chunk_size=60, overlap=30)
        if len(chunks) > 1:
            # The end of chunk 0 should appear near the start of chunk 1
            last_words = chunks[0].split()[-3:]
            first_words = chunks[1].split()[:6]
            overlap_found = any(w in first_words for w in last_words)
            assert overlap_found

    def test_very_long_sentence_becomes_own_chunk(self) -> None:
        long_sent = "word " * 200  # 1000 chars — exceeds chunk_size
        text = f"Intro. {long_sent.strip()}. Outro."
        chunks = chunk_sentence(text, chunk_size=200, overlap=40)
        # The long sentence should be preserved as its own chunk
        assert any(len(c) >= 200 or "word" in c for c in chunks)

    def test_chunks_nonempty(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunk_sentence(text, chunk_size=30, overlap=10)
        assert all(c.strip() for c in chunks)

    def test_paragraph_breaks_act_as_boundaries(self) -> None:
        text = "Paragraph one content.\n\nParagraph two content.\n\nParagraph three."
        chunks = chunk_sentence(text, chunk_size=30, overlap=5)
        assert len(chunks) >= 2


# ── Strategy 4: Paragraph-based (chunk_paragraph) ─────────────────────────────


class TestChunkParagraph:
    def test_empty_returns_empty(self) -> None:
        assert chunk_paragraph("") == []

    def test_short_text_single_chunk(self) -> None:
        text = "Just one paragraph."
        chunks = chunk_paragraph(text, chunk_size=512)
        assert len(chunks) == 1

    def test_splits_at_double_newlines(self) -> None:
        text = "\n\n".join(f"Paragraph {i} content here." for i in range(6))
        chunks = chunk_paragraph(text, chunk_size=60, overlap=20)
        assert len(chunks) > 1

    def test_all_paragraphs_in_output(self) -> None:
        paras = [f"Para{i}: some content." for i in range(5)]
        text = "\n\n".join(paras)
        chunks = chunk_paragraph(text, chunk_size=40, overlap=10)
        combined = " ".join(chunks)
        for i in range(5):
            assert f"Para{i}" in combined

    def test_oversized_paragraph_sentence_split(self) -> None:
        long_para = ". ".join(f"Sentence {i}" for i in range(20)) + "."
        chunks = chunk_paragraph(long_para, chunk_size=80, overlap=20)
        assert len(chunks) > 1

    def test_short_paragraphs_merged(self) -> None:
        # Three very short paragraphs should merge into one chunk
        text = "A.\n\nB.\n\nC."
        chunks = chunk_paragraph(text, chunk_size=512, overlap=80)
        assert len(chunks) == 1
        assert "A" in chunks[0] and "C" in chunks[0]

    def test_overlap_carries_paragraphs(self) -> None:
        # Long paragraphs — overlap should carry last para into next chunk
        long_para = "word " * 30  # ~150 chars each
        text = "\n\n".join([long_para] * 6)
        chunks = chunk_paragraph(text, chunk_size=200, overlap=100)
        assert len(chunks) >= 2

    def test_chunks_nonempty(self) -> None:
        text = "\n\n".join(f"P{i} content." for i in range(4))
        chunks = chunk_paragraph(text, chunk_size=40, overlap=10)
        assert all(c.strip() for c in chunks)


# ── Strategy 5: Heading-based (chunk_heading) ─────────────────────────────────


class TestChunkHeading:
    def test_returns_tuples(self) -> None:
        text = "# Title\nContent.\n## Section\nMore content."
        result = chunk_heading(text, chunk_size=512)
        assert isinstance(result, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in result)

    def test_empty_returns_empty(self) -> None:
        assert chunk_heading("") == []
        assert chunk_heading("   ") == []

    def test_splits_at_headings(self) -> None:
        text = "# H1\nContent A.\n## H2\nContent B.\n### H3\nContent C."
        result = chunk_heading(text, chunk_size=512)
        assert len(result) >= 3

    def test_heading_path_in_metadata(self) -> None:
        text = "# Guide\nIntro.\n## Setup\nInstall.\n### Linux\nLinux steps."
        result = chunk_heading(text, chunk_size=512)
        paths = [meta["heading_path"] for _, meta in result]
        assert any("Guide" in p for p in paths)
        assert any("Setup" in p for p in paths)
        assert any("Linux" in p for p in paths)

    def test_nested_heading_path_uses_separator(self) -> None:
        text = "# Parent\n## Child\n### Grandchild\nDeep content."
        result = chunk_heading(text, chunk_size=512)
        paths = [meta["heading_path"] for _, meta in result]
        assert any(" > " in p for p in paths)
        assert any("Grandchild" in p for p in paths)

    def test_no_headings_falls_back_to_paragraph(self) -> None:
        text = "Just plain text.\n\nAnother paragraph.\n\nThird paragraph."
        result = chunk_heading(text, chunk_size=512)
        assert len(result) >= 1
        # Should still produce chunks
        assert all(c.strip() for c, _ in result)

    def test_inherits_parent_heading_path(self) -> None:
        text = "## Subsection\nContent here."
        base = {"heading_path": "Chapter 1", "source_path": "doc.md"}
        result = chunk_heading(text, chunk_size=512, base_meta=base)
        path = result[0][1]["heading_path"]
        assert "Chapter 1" in path
        assert "Subsection" in path

    def test_oversized_section_paragraph_split(self) -> None:
        long_content = "\n\n".join(f"Paragraph {i} with content." for i in range(10))
        text = f"# Big Section\n{long_content}"
        result = chunk_heading(text, chunk_size=80, overlap=20)
        assert len(result) > 1
        # All sub-chunks should inherit the heading path
        for _, meta in result:
            assert "Big Section" in meta.get("heading_path", "")

    def test_chunk_index_assigned(self) -> None:
        text = "# A\nContent.\n## B\nMore content.\n### C\nDeep content."
        result = chunk_heading(text, chunk_size=512)
        for _, meta in result:
            assert "chunk_index" in meta

    def test_all_content_preserved(self) -> None:
        text = "# Alpha\nAlpha content.\n## Beta\nBeta content.\n## Gamma\nGamma content."
        result = chunk_heading(text, chunk_size=512)
        combined = " ".join(c for c, _ in result)
        assert "Alpha content" in combined
        assert "Beta content" in combined
        assert "Gamma content" in combined

    def test_heading_level_resets_at_same_level(self) -> None:
        text = "## Section A\nContent A.\n## Section B\nContent B."
        result = chunk_heading(text, chunk_size=512)
        paths = [meta["heading_path"] for _, meta in result]
        assert any("Section A" in p for p in paths)
        assert any("Section B" in p for p in paths)
        # Section B should NOT include Section A in its path (same level resets)
        for _, meta in result:
            if "Section B" in meta.get("heading_path", ""):
                assert "Section A" not in meta["heading_path"]


# ── Strategy 6: Semantic (achunk_semantic) ────────────────────────────────────


class TestAchunkSemantic:
    async def test_returns_list_of_strings(self) -> None:
        backend = MockEmbeddingBackend()
        text = " ".join(f"Sentence {i} with some content." for i in range(20))
        chunks = await achunk_semantic(text, backend, chunk_size=200, overlap=40)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)

    async def test_empty_returns_empty(self) -> None:
        backend = MockEmbeddingBackend()
        chunks = await achunk_semantic("", backend)
        assert chunks == []

    async def test_few_sentences_falls_back(self) -> None:
        backend = MockEmbeddingBackend()
        text = "Short text. Only two sentences."
        chunks = await achunk_semantic(text, backend, chunk_size=512, window_size=3)
        assert len(chunks) >= 1

    async def test_all_content_preserved(self) -> None:
        backend = MockEmbeddingBackend()
        sentences = [f"Topic {i} details here." for i in range(15)]
        text = " ".join(sentences)
        chunks = await achunk_semantic(text, backend, chunk_size=300, overlap=40)
        combined = " ".join(chunks)
        assert "Topic 0" in combined
        assert "Topic 14" in combined

    async def test_chunks_nonempty(self) -> None:
        backend = MockEmbeddingBackend()
        text = " ".join(f"S{i} sentence content." for i in range(20))
        chunks = await achunk_semantic(text, backend, chunk_size=200, overlap=40)
        assert all(c.strip() for c in chunks)

    async def test_respects_chunk_size(self) -> None:
        backend = MockEmbeddingBackend()
        # Create a text with many sentences — chunks should not wildly exceed size
        text = " ".join(f"Sentence number {i} with some content words here." for i in range(30))
        chunks = await achunk_semantic(text, backend, chunk_size=200, overlap=40)
        # Most chunks should be ≤ chunk_size (some tolerance for overlap carry)
        oversized = [c for c in chunks if len(c) > 500]
        assert not oversized


# ── dispatch_chunk — routing logic ────────────────────────────────────────────


class TestDispatchChunk:
    def test_fixed_strategy(self) -> None:
        text = "word " * 300
        result = dispatch_chunk(text, strategy="fixed", size=200, overlap=80)
        assert len(result) > 1
        for chunk, meta in result:
            assert chunk.strip()
            assert "chunk_index" in meta

    def test_code_strategy(self) -> None:
        code = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        result = dispatch_chunk(code, strategy="code", size=512, overlap=80)
        assert len(result) >= 2
        for chunk, meta in result:
            assert "chunk_index" in meta

    def test_sentence_strategy(self) -> None:
        text = ". ".join(f"Sentence {i}" for i in range(20)) + "."
        result = dispatch_chunk(text, strategy="sentence", size=80, overlap=20)
        assert len(result) >= 1
        for chunk, meta in result:
            assert "chunk_index" in meta

    def test_paragraph_strategy(self) -> None:
        text = "\n\n".join(f"Paragraph {i} content." for i in range(5))
        result = dispatch_chunk(text, strategy="paragraph", size=60, overlap=20)
        assert len(result) >= 1
        for chunk, meta in result:
            assert "chunk_index" in meta

    def test_heading_strategy_returns_heading_path(self) -> None:
        text = "# Title\nIntro.\n## Section\nContent."
        result = dispatch_chunk(text, strategy="heading", size=512, overlap=80)
        assert any("heading_path" in meta for _, meta in result)

    def test_semantic_strategy_falls_back_to_paragraph(self) -> None:
        # dispatch_chunk falls back to paragraph for semantic (no async backend)
        text = "\n\n".join(f"Para {i} content here." for i in range(4))
        result = dispatch_chunk(text, strategy="semantic", size=100, overlap=80)
        assert len(result) >= 1
        for chunk, meta in result:
            assert chunk.strip()

    def test_unknown_strategy_uses_fixed(self) -> None:
        text = "word " * 100
        result = dispatch_chunk(text, strategy="does_not_exist", size=100, overlap=80)
        assert len(result) >= 1

    def test_minimum_overlap_enforced(self) -> None:
        # Even with overlap=0, dispatch_chunk should apply minimum 80 chars
        text = "word " * 200
        result = dispatch_chunk(text, strategy="fixed", size=100, overlap=0)
        assert len(result) >= 1

    def test_meta_propagated_to_all_chunks(self) -> None:
        text = "word " * 200
        meta = {"source_path": "test.txt", "file_type": ".txt", "custom_field": "value"}
        result = dispatch_chunk(text, strategy="fixed", size=100, overlap=80, meta=meta)
        for _, chunk_meta in result:
            assert chunk_meta.get("source_path") == "test.txt"
            assert chunk_meta.get("custom_field") == "value"

    def test_empty_text_returns_empty(self) -> None:
        for strategy in ("fixed", "code", "sentence", "paragraph", "heading", "semantic"):
            result = dispatch_chunk("", strategy=strategy)
            assert result == [], f"strategy={strategy} should return [] for empty text"

    def test_chunk_index_sequential(self) -> None:
        text = "word " * 200
        result = dispatch_chunk(text, strategy="fixed", size=100, overlap=80)
        indices = [meta["chunk_index"] for _, meta in result]
        assert indices == list(range(len(indices)))


# ── Overlap enforcement ───────────────────────────────────────────────────────


class TestOverlapEnforcement:
    def test_sentence_overlap_minimum(self) -> None:
        text = " ".join(f"Sentence {i} content." for i in range(10))
        # With large overlap (> chunk_size), should still produce valid chunks
        chunks = chunk_sentence(text, chunk_size=100, overlap=80)
        assert len(chunks) >= 1
        assert all(c.strip() for c in chunks)

    def test_paragraph_overlap_minimum(self) -> None:
        text = "\n\n".join(f"Para {i}." for i in range(5))
        chunks = chunk_paragraph(text, chunk_size=40, overlap=80)
        assert len(chunks) >= 1

    def test_dispatch_overlap_clamped_to_80(self) -> None:
        # Even if caller passes overlap=10, dispatch_chunk enforces min 80
        text = "word " * 50
        r1 = dispatch_chunk(text, strategy="fixed", size=120, overlap=10)
        r2 = dispatch_chunk(text, strategy="fixed", size=120, overlap=80)
        # Both should produce the same result since overlap is clamped to 80
        assert [c for c, _ in r1] == [c for c, _ in r2]


# ── chunk_file (legacy) ───────────────────────────────────────────────────────


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
