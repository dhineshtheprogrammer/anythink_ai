"""AttributionFormatter — pure Rich Text helpers for MMOS response attribution (V4).

No Textual dependency; safe to use in both TUI and CLI render paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

if TYPE_CHECKING:
    from anythink.optimize.models import TurnMMOSMetadata
    from anythink.optimize.plan import PlanPhase

_BAR_CHAR = "─"
_ENSEMBLE_SEPARATOR = "═"


class AttributionFormatter:
    """Static helpers that produce Rich Text attribution lines for MMOS output."""

    @staticmethod
    def single_model_header(
        model_id: str,
        strategy: str,
        tokens: int,
        elapsed_s: float,
        *,
        width: int = 80,
    ) -> Text:
        """Produce a compact attribution header for a single-model response.

        Example output:
            ── groq/llama3-70b  ·  routing  ·  1,243 tokens  ·  0.8s ──
        """
        body = (
            f" {model_id}  ·  {strategy}  ·  {tokens:,} tokens  ·  {elapsed_s:.1f}s "
        )
        total = width - 4
        pad = max(0, total - len(body))
        left = _BAR_CHAR * 2
        right = _BAR_CHAR * (pad + 2)

        line = Text()
        line.append(left, style="dim")
        line.append(body, style="dim")
        line.append(right, style="dim")
        return line

    @staticmethod
    def plan_mode_header(
        mmos: TurnMMOSMetadata,
        *,
        phase_count: int = 0,
        width: int = 80,
    ) -> Text:
        """Produce an attribution header for a Plan Mode response.

        Example output:
            ── Plan Mode  ·  5 phases  ·  groq, together, ollama  ·  4,821 tokens  ·  2m 14s ──
        """
        unique_providers = list(
            dict.fromkeys(m.split("/")[0] for m in mmos.model_ids if "/" in m)
        )
        providers_str = ", ".join(unique_providers[:4]) if unique_providers else "?"
        phases_str = f"{phase_count} phases" if phase_count else "plan"
        elapsed_str = _format_elapsed(mmos.elapsed_s)

        body = (
            f" Plan Mode  ·  {phases_str}  ·  {providers_str}"
            f"  ·  {mmos.total_tokens:,} tokens  ·  {elapsed_str} "
        )
        pad = max(0, width - len(body) - 4)
        left = _BAR_CHAR * 2
        right = _BAR_CHAR * (pad + 2)

        line = Text()
        line.append(left, style="dim")
        line.append(body, style="dim")
        line.append(right, style="dim")
        return line

    @staticmethod
    def ensemble_section_header(
        model_id: str,
        index: int,
        total: int,
        speed_class: str,
        *,
        width: int = 80,
    ) -> Text:
        """Produce a section header separating ensemble responses.

        Example output:
            ════════  Response 1 of 3  ·  groq/llama3-70b  ·  [fast]  ════════
        """
        body = f"  Response {index} of {total}  ·  {model_id}  ·  [{speed_class}]  "
        pad = max(0, width - len(body) - 16)
        left = _ENSEMBLE_SEPARATOR * 8
        right = _ENSEMBLE_SEPARATOR * (pad + 8)

        line = Text()
        line.append(left, style="bold dim")
        line.append(body, style="bold")
        line.append(right, style="bold dim")
        return line

    @staticmethod
    def phase_output_block(
        phase: PlanPhase,
        *,
        width: int = 80,
    ) -> Text:
        """Produce a section header for an expanded phase output block.

        Example output:
            ── Phase 2: Frontend architecture  ·  groq/llama3-70b  ·  0.8s ──
        """
        model = phase.actual_model or phase.model_id
        body = f" Phase {phase.phase_num}: {phase.title}  ·  {model}  ·  {phase.elapsed_s:.1f}s "
        pad = max(0, width - len(body) - 4)
        left = _BAR_CHAR * 2
        right = _BAR_CHAR * (pad + 2)

        line = Text()
        line.append(left, style="dim")
        line.append(body, style="dim italic")
        line.append(right, style="dim")
        return line

    @staticmethod
    def from_mmos_metadata(
        mmos: TurnMMOSMetadata,
        *,
        width: int = 80,
    ) -> Text:
        """Choose the appropriate header type from a TurnMMOSMetadata object."""
        if mmos.strategy in ("decompose", "plan") and mmos.phase_outputs:
            return AttributionFormatter.plan_mode_header(
                mmos, phase_count=len(mmos.phase_outputs), width=width
            )
        return AttributionFormatter.single_model_header(
            model_id=", ".join(mmos.model_ids[:2]) if mmos.model_ids else "?",
            strategy=mmos.strategy,
            tokens=mmos.total_tokens,
            elapsed_s=mmos.elapsed_s,
            width=width,
        )


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-friendly string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs:02d}s"
