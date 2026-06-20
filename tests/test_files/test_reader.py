"""Tests for files/reader.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from anythink.exceptions import FileError
from anythink.files.reader import (
    MAX_IMAGE_BYTES,
    MAX_TEXT_BYTES,
    ImageAttachment,
    TextAttachment,
    read_file,
    read_image_file,
    read_text_file,
)
from anythink.providers.base import ImagePart

# ── read_text_file ────────────────────────────────────────────────────────────


class TestReadTextFile:
    def test_returns_text_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.py"
        f.write_text("print('hello')", encoding="utf-8")
        att = read_text_file(f)
        assert isinstance(att, TextAttachment)

    def test_content_matches_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        att = read_text_file(f)
        assert att.content == '{"key": "value"}'

    def test_filename_in_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello", encoding="utf-8")
        att = read_text_file(f)
        assert att.filename == "readme.md"

    def test_size_bytes_in_attachment(self, tmp_path: Path) -> None:
        content = "hello world"
        f = tmp_path / "note.txt"
        f.write_text(content, encoding="utf-8")
        att = read_text_file(f)
        assert att.size_bytes == len(content.encode("utf-8"))

    def test_path_stored(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value", encoding="utf-8")
        att = read_text_file(f)
        assert att.path == f.resolve()

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileError, match="not found"):
            read_text_file(tmp_path / "missing.py")

    def test_image_extension_raises_with_hint(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.png"
        f.write_bytes(b"\x89PNG")
        with pytest.raises(FileError, match="/image"):
            read_text_file(f)

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK")
        with pytest.raises(FileError, match="Unsupported"):
            read_text_file(f)

    def test_file_too_large_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        f.write_bytes(b"x" * (MAX_TEXT_BYTES + 1))
        with pytest.raises(FileError, match="too large"):
            read_text_file(f)

    def test_binary_content_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.py"
        f.write_bytes(b"\x00\x01\x02\xff\xfe")
        with pytest.raises(FileError, match="binary"):
            read_text_file(f)

    @pytest.mark.parametrize(
        "ext",
        [
            ".py",
            ".js",
            ".ts",
            ".go",
            ".rs",
            ".json",
            ".yaml",
            ".md",
            ".txt",
            ".csv",
            ".toml",
            ".log",
        ],
    )
    def test_supported_extensions_accepted(self, tmp_path: Path, ext: str) -> None:
        f = tmp_path / f"file{ext}"
        f.write_text("content", encoding="utf-8")
        att = read_text_file(f)
        assert att.content == "content"


# ── read_image_file ───────────────────────────────────────────────────────────


class TestReadImageFile:
    def test_returns_image_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        att = read_image_file(f)
        assert isinstance(att, ImageAttachment)

    def test_image_part_is_image_part(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.png"
        f.write_bytes(b"\x89PNG")
        att = read_image_file(f)
        assert isinstance(att.image_part, ImagePart)

    def test_png_mime_type(self, tmp_path: Path) -> None:
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG")
        assert read_image_file(f).image_part.mime_type == "image/png"

    def test_jpg_mime_type(self, tmp_path: Path) -> None:
        f = tmp_path / "img.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        assert read_image_file(f).image_part.mime_type == "image/jpeg"

    def test_jpeg_mime_type(self, tmp_path: Path) -> None:
        f = tmp_path / "img.jpeg"
        f.write_bytes(b"\xff\xd8\xff")
        assert read_image_file(f).image_part.mime_type == "image/jpeg"

    def test_webp_mime_type(self, tmp_path: Path) -> None:
        f = tmp_path / "img.webp"
        f.write_bytes(b"RIFF")
        assert read_image_file(f).image_part.mime_type == "image/webp"

    def test_gif_mime_type(self, tmp_path: Path) -> None:
        f = tmp_path / "img.gif"
        f.write_bytes(b"GIF89a")
        assert read_image_file(f).image_part.mime_type == "image/gif"

    def test_bytes_preserved(self, tmp_path: Path) -> None:
        raw = b"\x89PNG\r\n\x1a\nsome image data"
        f = tmp_path / "img.png"
        f.write_bytes(raw)
        att = read_image_file(f)
        assert att.image_part.data == raw

    def test_filename_in_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "diagram.png"
        f.write_bytes(b"\x89PNG")
        att = read_image_file(f)
        assert att.filename == "diagram.png"

    def test_size_bytes_in_attachment(self, tmp_path: Path) -> None:
        raw = b"\x89PNG\r\n"
        f = tmp_path / "s.png"
        f.write_bytes(raw)
        att = read_image_file(f)
        assert att.size_bytes == len(raw)

    def test_image_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileError, match="not found"):
            read_image_file(tmp_path / "missing.png")

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.bmp"
        f.write_bytes(b"BM")
        with pytest.raises(FileError, match="supported image"):
            read_image_file(f)

    def test_text_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.py"
        f.write_text("print()", encoding="utf-8")
        with pytest.raises(FileError, match="supported image"):
            read_image_file(f)

    def test_image_too_large_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "huge.png"
        f.write_bytes(b"\x89" * (MAX_IMAGE_BYTES + 1))
        with pytest.raises(FileError, match="too large"):
            read_image_file(f)


# ── read_file (auto-detect) ───────────────────────────────────────────────────


class TestReadFile:
    def test_routes_text_to_text_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "main.py"
        f.write_text("# hello", encoding="utf-8")
        att = read_file(f)
        assert isinstance(att, TextAttachment)

    def test_routes_image_to_image_attachment(self, tmp_path: Path) -> None:
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        att = read_file(f)
        assert isinstance(att, ImageAttachment)

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.pdf"
        f.write_bytes(b"%PDF")
        with pytest.raises(FileError, match="Unsupported"):
            read_file(f)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileError, match="not found"):
            read_file(tmp_path / "nope.txt")
