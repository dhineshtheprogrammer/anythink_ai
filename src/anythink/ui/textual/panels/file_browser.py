"""Bottom-tab panel: local file browser backed by the Filesystem MCP server."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Input, Static


class FileBrowserTab(Widget):
    """Tab pane that lets the user browse the local filesystem."""

    DEFAULT_CSS = """
    FileBrowserTab {
        height: 1fr;
        padding: 0 1;
    }
    FileBrowserTab Input {
        height: 1;
        margin-bottom: 0;
    }
    FileBrowserTab VerticalScroll {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Path (Enter to list)…", id="fb-path")
        yield VerticalScroll(
            Static("[dim]Enter a directory path above to browse.[/dim]", id="fb-listing"),
            id="fb-scroll",
        )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """List the directory when the user presses Enter."""
        from anythink.mcp.builtin.filesystem import FilesystemServer

        path = event.value.strip() or "."
        srv = FilesystemServer()
        result = await srv.call_tool("list_dir", {"path": path})
        listing = self.query_one("#fb-listing", Static)
        if result.is_error:
            listing.update(f"[red]Error:[/red] {result.content}")
        else:
            listing.update(result.content)
