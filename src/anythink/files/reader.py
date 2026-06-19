"""File reader — reads text and image files for chat attachment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anythink.exceptions import FileError
from anythink.providers.base import ImagePart

SUPPORTED_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".cpp", ".c", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
    ".json", ".yaml", ".yml", ".csv", ".xml", ".toml", ".env",
    ".ini", ".cfg", ".md", ".txt", ".rst", ".log",
})

SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
})

_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

MAX_TEXT_BYTES: int = 1 * 1024 * 1024    # 1 MB
MAX_IMAGE_BYTES: int = 10 * 1024 * 1024  # 10 MB


@dataclass
class TextAttachment:
    path: Path
    filename: str
    content: str
    size_bytes: int


@dataclass
class ImageAttachment:
    path: Path
    filename: str
    image_part: ImagePart
    size_bytes: int


FileAttachment = TextAttachment | ImageAttachment


def read_file(path: str | Path) -> FileAttachment:
    """Read any supported file; auto-detects text vs image by extension.

    Raises FileError for: not found, unsupported extension, too large, or
    undecodable binary content in a text-extension file.
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileError(
            f"File not found: {path}",
            user_message=f"File not found: {path}",
        )

    suffix = resolved.suffix.lower()

    if suffix in SUPPORTED_IMAGE_EXTENSIONS:
        return _read_image(resolved, suffix)

    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return _read_text(resolved)

    raise FileError(
        f"Unsupported file extension '{suffix}': {resolved.name}",
        user_message=(
            f"Unsupported file type '{suffix}'. "
            f"Supported text formats: {', '.join(sorted(SUPPORTED_TEXT_EXTENSIONS))}. "
            f"Supported image formats: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}."
        ),
    )


def read_text_file(path: str | Path) -> TextAttachment:
    """Read a text file. Raises FileError if the extension is not a supported text type."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileError(f"File not found: {path}", user_message=f"File not found: {path}")

    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_TEXT_EXTENSIONS:
        if suffix in SUPPORTED_IMAGE_EXTENSIONS:
            raise FileError(
                f"'{resolved.name}' is an image — use /image to attach images.",
                user_message=f"'{resolved.name}' is an image file. Use /image to attach images.",
            )
        raise FileError(
            f"Unsupported text extension '{suffix}'",
            user_message=f"Unsupported file type '{suffix}' for /file. Supported: {', '.join(sorted(SUPPORTED_TEXT_EXTENSIONS))}.",
        )

    return _read_text(resolved)


def read_image_file(path: str | Path) -> ImageAttachment:
    """Read an image file. Raises FileError if the extension is not a supported image type."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileError(f"File not found: {path}", user_message=f"File not found: {path}")

    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise FileError(
            f"Not a supported image format '{suffix}'",
            user_message=(
                f"Unsupported image format '{suffix}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}."
            ),
        )

    return _read_image(resolved, suffix)


def _read_text(resolved: Path) -> TextAttachment:
    size = resolved.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise FileError(
            f"Text file too large: {size} bytes (max {MAX_TEXT_BYTES})",
            user_message=(
                f"File '{resolved.name}' is too large "
                f"({size / 1024:.1f} KB). Maximum is {MAX_TEXT_BYTES // 1024} KB."
            ),
        )
    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise FileError(
            f"File '{resolved.name}' is not valid UTF-8 text",
            user_message=f"File '{resolved.name}' appears to be a binary file and cannot be read as text.",
        )
    return TextAttachment(path=resolved, filename=resolved.name, content=content, size_bytes=size)


def _read_image(resolved: Path, suffix: str) -> ImageAttachment:
    size = resolved.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise FileError(
            f"Image too large: {size} bytes (max {MAX_IMAGE_BYTES})",
            user_message=(
                f"Image '{resolved.name}' is too large "
                f"({size / 1024 / 1024:.1f} MB). Maximum is {MAX_IMAGE_BYTES // 1024 // 1024} MB."
            ),
        )
    data = resolved.read_bytes()
    mime_type = _MIME_TYPES[suffix]
    return ImageAttachment(
        path=resolved,
        filename=resolved.name,
        image_part=ImagePart(data=data, mime_type=mime_type),
        size_bytes=size,
    )
