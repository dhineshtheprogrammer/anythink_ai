"""Output writers for batch processing results."""

from __future__ import annotations

import json
from pathlib import Path

from anythink.batch.runner import BatchResult


def write_markdown(results: list[BatchResult], output: Path) -> None:
    """Write batch results as a Markdown file."""
    lines: list[str] = ["# Batch Run Results", ""]
    for r in results:
        lines.append(f"## Prompt {r.index + 1}")
        lines.append("")
        lines.append(f"**Input:** {r.prompt}")
        lines.append("")
        if r.error:
            lines.append(f"**Error:** {r.error}")
        else:
            lines.append("**Response:**")
            lines.append("")
            lines.append(r.response)
            if r.usage:
                lines.append(
                    f"\n_Tokens: {r.usage.prompt_tokens} prompt + "
                    f"{r.usage.completion_tokens} completion — "
                    f"{r.elapsed_s:.1f}s_"
                )
        lines.append("")
        lines.append("---")
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def write_json(results: list[BatchResult], output: Path) -> None:
    """Write batch results as a JSON file."""
    data = [
        {
            "index": r.index,
            "prompt": r.prompt,
            "response": r.response,
            "error": r.error,
            "elapsed_s": r.elapsed_s,
            "usage": (
                {
                    "prompt_tokens": r.usage.prompt_tokens,
                    "completion_tokens": r.usage.completion_tokens,
                    "total_tokens": r.usage.total_tokens,
                }
                if r.usage
                else None
            ),
        }
        for r in results
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
