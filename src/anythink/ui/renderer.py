"""Two-phase streaming response renderer using Rich."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from anythink.providers.base import StreamChunk, TokenUsage
from anythink.ui.theme import Theme


@dataclass
class StreamRenderer:
    """Renders provider stream chunks to the terminal in two phases.

    Phase 1: accumulates text inside a Live block for instant feedback.
    Phase 2: replaces the live block with formatted Markdown on completion.
    """

    console: Console
    theme: Theme

    async def stream(
        self,
        chunks: AsyncIterator[StreamChunk],
        *,
        refresh_per_second: int = 15,
    ) -> tuple[str, TokenUsage | None]:
        """Consume an async chunk stream and render it live.

        Returns (full_text, usage) when the stream is exhausted.
        """
        buffer: list[str] = []
        usage: TokenUsage | None = None

        with Live(
            Text("", style=self.theme.primary),
            console=self.console,
            refresh_per_second=refresh_per_second,
            transient=False,
        ) as live:
            async for chunk in chunks:
                if chunk.text:
                    buffer.append(chunk.text)
                    live.update(Text("".join(buffer), style=self.theme.primary))
                if chunk.usage:
                    usage = chunk.usage

            # Phase 2: replace live plain text with rendered Markdown
            full_text = "".join(buffer)
            if full_text:
                live.update(Markdown(full_text))

        return full_text, usage
