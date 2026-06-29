"""Windows Filesystem MCP server — full file and folder management within allowed paths."""

from __future__ import annotations

import fnmatch
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from anythink.mcp.builtin.base import BuiltinMCPServer
from anythink.mcp.models import MCPCallResult, MCPTool
from anythink.mcp.windows.audit import WindowsAuditLog
from anythink.mcp.windows.paths import WindowsPathGuard
from anythink.mcp.windows.safety import WindowsSafetyChecker

_WINDOWS_ONLY = sys.platform == "win32"
_WIN_ERR = f"This tool requires Windows. Current platform: {sys.platform}"
_MAX_WRITE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_SEARCH_RESULTS = 200
_MAX_SEARCH_DEPTH = 5

# All tool names exposed by this server — used for tool count verification
_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_dir",
        "read_file",
        "get_file_metadata",
        "search_files_by_name",
        "search_files_by_content",
        "write_file",
        "create_file",
        "create_folder",
        "copy_file",
        "move_file",
        "rename_file",
        "delete_file",
        "delete_folder",
    }
)


class WindowsFilesystemServer(BuiltinMCPServer):
    """Full file and folder management on Windows within allowed paths."""

    name = "windows-filesystem"
    description = "Full file and folder management on Windows within allowed paths."

    def __init__(
        self,
        path_guard: WindowsPathGuard,
        safety: WindowsSafetyChecker,
        audit: WindowsAuditLog,
    ) -> None:
        self._path_guard = path_guard
        self._safety = safety
        self._audit = audit

    def list_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                "list_dir",
                "List contents of a directory with names, types, and sizes.",
                {
                    "path": {"type": "string", "description": "Directory path"},
                    "show_hidden": {"type": "boolean", "description": "Include hidden files", "default": False},
                },
                self.name,
            ),
            MCPTool(
                "read_file",
                "Read the text content of a file.",
                {
                    "path": {"type": "string", "description": "File path"},
                    "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
                },
                self.name,
            ),
            MCPTool(
                "get_file_metadata",
                "Get size, creation date, modified date, and permissions for a file or folder.",
                {"path": {"type": "string", "description": "File or folder path"}},
                self.name,
            ),
            MCPTool(
                "search_files_by_name",
                "Recursively search for files matching a name pattern (supports * and ?).",
                {
                    "root_path": {"type": "string", "description": "Root directory to search"},
                    "pattern": {"type": "string", "description": "Name pattern (e.g. *.py, config*.json)"},
                    "recursive": {"type": "boolean", "description": "Search recursively", "default": True},
                },
                self.name,
            ),
            MCPTool(
                "search_files_by_content",
                "Search files containing a specific text string.",
                {
                    "root_path": {"type": "string", "description": "Root directory to search"},
                    "query": {"type": "string", "description": "Text string to find (case-insensitive)"},
                    "file_extensions": {"type": "array", "description": "File extensions to search (e.g. ['.txt', '.py'])"},
                    "recursive": {"type": "boolean", "description": "Search recursively", "default": True},
                },
                self.name,
            ),
            MCPTool(
                "write_file",
                "Write text content to a file. Tier 2 for new files, Tier 3 if overwriting.",
                {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Text content to write"},
                    "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
                    "overwrite": {"type": "boolean", "description": "Overwrite if file exists", "default": False},
                },
                self.name,
            ),
            MCPTool(
                "create_file",
                "Create a new empty file at the specified path.",
                {"path": {"type": "string", "description": "File path to create"}},
                self.name,
            ),
            MCPTool(
                "create_folder",
                "Create a new folder (including all intermediate directories).",
                {
                    "path": {"type": "string", "description": "Folder path to create"},
                    "exist_ok": {"type": "boolean", "description": "Don't error if folder already exists", "default": True},
                },
                self.name,
            ),
            MCPTool(
                "copy_file",
                "Copy a file to a destination. Tier 2 if destination is new, Tier 3 if overwriting.",
                {
                    "source": {"type": "string", "description": "Source file path"},
                    "destination": {"type": "string", "description": "Destination file path"},
                    "overwrite": {"type": "boolean", "description": "Overwrite destination if it exists", "default": False},
                },
                self.name,
            ),
            MCPTool(
                "move_file",
                "Move a file or folder to a new location.",
                {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                },
                self.name,
            ),
            MCPTool(
                "rename_file",
                "Rename a file or folder (stays in same directory).",
                {
                    "path": {"type": "string", "description": "Current file/folder path"},
                    "new_name": {"type": "string", "description": "New filename (not a full path)"},
                },
                self.name,
            ),
            MCPTool(
                "delete_file",
                "Permanently delete a file.",
                {"path": {"type": "string", "description": "File path to delete"}},
                self.name,
            ),
            MCPTool(
                "delete_folder",
                "Delete a folder. Tier 3 if empty, Tier 4 if recursive (non-empty).",
                {
                    "path": {"type": "string", "description": "Folder path to delete"},
                    "recursive": {"type": "boolean", "description": "Delete non-empty folder and all contents", "default": False},
                },
                self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPCallResult:
        t0 = time.monotonic()
        tier = self._safety.get_tier(self.name, name, **arguments)

        # Validate all path arguments before executing
        paths_to_validate: list[str] = []
        for key in ("path", "source", "root_path"):
            if key in arguments:
                paths_to_validate.append(str(arguments[key]))
        if "destination" in arguments:
            # Only validate destination parent for copy/move (destination may not exist yet)
            dest = str(arguments["destination"])
            parent = os.path.dirname(os.path.abspath(dest))
            paths_to_validate.append(parent)

        for p in paths_to_validate:
            err = self._path_guard.validate(p)
            if err:
                self._audit.log(
                    session_id="",
                    server=self.name,
                    tool=name,
                    tier=tier,
                    arguments=arguments,
                    confirmation_status="not_required",
                    outcome="blocked_by_path_guard",
                    duration_s=round(time.monotonic() - t0, 4),
                    error=err,
                )
                return MCPCallResult(
                    tool_name=name,
                    server_name=self.name,
                    content=err,
                    is_error=True,
                    duration_s=round(time.monotonic() - t0, 3),
                )

        try:
            content = self._dispatch(name, arguments)
            outcome = "success"
            error = None
        except Exception as exc:
            content = str(exc)
            outcome = "error"
            error = str(exc)

        duration = round(time.monotonic() - t0, 3)
        self._audit.log(
            session_id="",
            server=self.name,
            tool=name,
            tier=tier,
            arguments={k: v for k, v in arguments.items() if k != "content"},
            confirmation_status="not_required" if tier == 1 else "auto",
            outcome=outcome,
            duration_s=duration,
            error=error,
        )
        return MCPCallResult(
            tool_name=name,
            server_name=self.name,
            content=content,
            is_error=error is not None,
            duration_s=duration,
        )

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        if not _WINDOWS_ONLY:
            return _WIN_ERR
        if name == "list_dir":
            path = str(arguments.get("path", "")).strip()
            if not path:
                raise ValueError("path argument is required. Usage: /mcp call list_dir path=<directory>")
            return self._list_dir(path, bool(arguments.get("show_hidden", False)))
        if name == "read_file":
            path = str(arguments.get("path", "")).strip()
            if not path:
                raise ValueError("path argument is required. Usage: /mcp call read_file path=<file>")
            return self._read_file(path, str(arguments.get("encoding", "utf-8")))
        if name == "get_file_metadata":
            return self._get_metadata(str(arguments.get("path", "")))
        if name == "search_files_by_name":
            return self._search_by_name(
                root=str(arguments.get("root_path", "")),
                pattern=str(arguments.get("pattern", "*")),
                recursive=bool(arguments.get("recursive", True)),
            )
        if name == "search_files_by_content":
            return self._search_by_content(
                root=str(arguments.get("root_path", "")),
                query=str(arguments.get("query", "")),
                extensions=arguments.get("file_extensions"),
                recursive=bool(arguments.get("recursive", True)),
            )
        if name == "write_file":
            return self._write_file(
                path=str(arguments.get("path", "")),
                content=str(arguments.get("content", "")),
                encoding=str(arguments.get("encoding", "utf-8")),
                overwrite=bool(arguments.get("overwrite", False)),
            )
        if name == "create_file":
            return self._create_file(str(arguments.get("path", "")))
        if name == "create_folder":
            return self._create_folder(str(arguments.get("path", "")), bool(arguments.get("exist_ok", True)))
        if name == "copy_file":
            return self._copy_file(
                source=str(arguments.get("source", "")),
                destination=str(arguments.get("destination", "")),
                overwrite=bool(arguments.get("overwrite", False)),
            )
        if name == "move_file":
            return self._move_file(str(arguments.get("source", "")), str(arguments.get("destination", "")))
        if name == "rename_file":
            return self._rename_file(str(arguments.get("path", "")), str(arguments.get("new_name", "")))
        if name == "delete_file":
            return self._delete_file(str(arguments.get("path", "")))
        if name == "delete_folder":
            return self._delete_folder(str(arguments.get("path", "")), bool(arguments.get("recursive", False)))
        raise ValueError(f"Unknown tool '{name}'")

    # ---------------------------------------------------------------- read ops

    def _list_dir(self, path: str, show_hidden: bool) -> str:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Path not found: {p}")
        if p.is_file():
            raise NotADirectoryError(f"Not a directory: {p}. Use read_file to read a file.")
        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        if not show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        lines = [f"{p}  ({len(entries)} items)", "─" * 50]
        for e in entries:
            kind = "📁" if e.is_dir() else "📄"
            if e.is_dir():
                lines.append(f"{kind}  {e.name + os.sep:<40} [folder]")
            else:
                try:
                    size = e.stat().st_size
                    size_str = f"{size // 1024} KB" if size >= 1024 else f"{size} B"
                except OSError:
                    size_str = "?"
                lines.append(f"{kind}  {e.name:<40} {size_str}")
        return "\n".join(lines)

    def _read_file(self, path: str, encoding: str) -> str:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        if not p.is_file():
            raise IsADirectoryError(f"Not a file: {p}")
        MAX = 50_000
        text = p.read_text(encoding=encoding, errors="replace")
        if len(text) > MAX:
            return text[:MAX] + f"\n[truncated — file has {len(text):,} characters, showing first {MAX:,}]"
        return text

    def _get_metadata(self, path: str) -> str:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Not found: {p}")
        stat = p.stat()
        import datetime
        created = datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(sep=" ", timespec="seconds")
        modified = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
        accessed = datetime.datetime.fromtimestamp(stat.st_atime).isoformat(sep=" ", timespec="seconds")
        readable = os.access(str(p), os.R_OK)
        writable = os.access(str(p), os.W_OK)
        return (
            f"Path:       {p}\n"
            f"Type:       {'File' if p.is_file() else 'Folder'}\n"
            f"Size:       {stat.st_size:,} bytes ({stat.st_size // 1024} KB)\n"
            f"Created:    {created}\n"
            f"Modified:   {modified}\n"
            f"Accessed:   {accessed}\n"
            f"Readable:   {'✓' if readable else '✗'}\n"
            f"Writable:   {'✓' if writable else '✗'}"
        )

    def _search_by_name(self, root: str, pattern: str, recursive: bool) -> str:
        root_p = Path(root).resolve()
        if not root_p.is_dir():
            return f"Not a directory: {root}"
        results: list[str] = []
        walker = os.walk(root_p)
        for depth, (dirpath, dirnames, filenames) in enumerate(walker):
            if depth >= _MAX_SEARCH_DEPTH:
                dirnames.clear()
                break
            for fname in filenames:
                if fnmatch.fnmatch(fname, pattern) or fnmatch.fnmatch(fname.lower(), pattern.lower()):
                    results.append(os.path.join(dirpath, fname))
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        break
            if not recursive:
                dirnames.clear()
        lines = [f"Search results for '{pattern}' in {root_p}:", "─" * 60]
        if results:
            lines.extend(results)
            if len(results) == _MAX_SEARCH_RESULTS:
                lines.append(f"[Results capped at {_MAX_SEARCH_RESULTS}]")
        else:
            lines.append("No matching files found.")
        return "\n".join(lines)

    def _search_by_content(
        self,
        root: str,
        query: str,
        extensions: Any,
        recursive: bool,
    ) -> str:
        root_p = Path(root).resolve()
        if not root_p.is_dir():
            return f"Not a directory: {root}"
        text_exts = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".log", ".ini", ".cfg", ".toml", ".xml", ".html", ".js", ".ts"}
        if extensions:
            filter_exts = {(e if e.startswith(".") else "." + e).lower() for e in extensions}
        else:
            filter_exts = text_exts
        query_lower = query.lower()
        results: list[str] = []

        for depth, (dirpath, dirnames, filenames) in enumerate(os.walk(root_p)):
            if depth >= _MAX_SEARCH_DEPTH:
                dirnames.clear()
                break
            for fname in filenames:
                if Path(fname).suffix.lower() not in filter_exts:
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    text = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                    if query_lower in text.lower():
                        results.append(fpath)
                        if len(results) >= _MAX_SEARCH_RESULTS:
                            break
                except OSError:
                    pass
            if not recursive:
                dirnames.clear()

        lines = [f"Content search for '{query}' in {root_p}:", "─" * 60]
        if results:
            lines.extend(results)
            if len(results) == _MAX_SEARCH_RESULTS:
                lines.append(f"[Results capped at {_MAX_SEARCH_RESULTS}]")
        else:
            lines.append("No matching files found.")
        return "\n".join(lines)

    # --------------------------------------------------------------- write ops

    def _write_file(self, path: str, content: str, encoding: str, overwrite: bool) -> str:
        p = Path(path).resolve()
        if p.exists() and not overwrite:
            return (
                f"File '{p}' already exists. Set overwrite=true to replace it. "
                "Warning: overwriting requires Tier 3 confirmation."
            )
        encoded = content.encode(encoding, errors="replace")
        if len(encoded) > _MAX_WRITE_BYTES:
            return (
                f"Content too large ({len(encoded):,} bytes). "
                f"Maximum write size is {_MAX_WRITE_BYTES // (1024*1024)} MB."
            )
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding, errors="replace")
        return f"File written: '{p}' ({len(encoded):,} bytes)."

    def _create_file(self, path: str) -> str:
        p = Path(path).resolve()
        if p.exists():
            return f"'{p}' already exists."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return f"File created: '{p}'."

    def _create_folder(self, path: str, exist_ok: bool) -> str:
        p = Path(path).resolve()
        p.mkdir(parents=True, exist_ok=exist_ok)
        return f"Folder created: '{p}'."

    def _copy_file(self, source: str, destination: str, overwrite: bool) -> str:
        src = Path(source).resolve()
        dst = Path(destination).resolve()
        if not src.exists():
            return f"Source not found: '{src}'."
        if dst.exists() and not overwrite:
            return (
                f"Destination '{dst}' already exists. Set overwrite=true to replace it. "
                "Warning: overwriting requires Tier 3 confirmation."
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return f"'{src}' copied to '{dst}'."

    def _move_file(self, source: str, destination: str) -> str:
        src = Path(source).resolve()
        dst = Path(destination).resolve()
        if not src.exists():
            return f"Source not found: '{src}'."
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"'{src}' moved to '{dst}'."

    def _rename_file(self, path: str, new_name: str) -> str:
        p = Path(path).resolve()
        if not p.exists():
            return f"Not found: '{p}'."
        if os.sep in new_name or "/" in new_name:
            return "new_name must be a filename only, not a path."
        new_path = p.parent / new_name
        p.rename(new_path)
        return f"Renamed to '{new_path}'."

    def _delete_file(self, path: str) -> str:
        p = Path(path).resolve()
        if not p.exists():
            return f"File not found: '{p}'."
        if not p.is_file():
            return f"'{p}' is not a file. Use delete_folder to remove directories."
        p.unlink()
        return f"File deleted: '{p}'."

    def _delete_folder(self, path: str, recursive: bool) -> str:
        p = Path(path).resolve()
        if not p.exists():
            return f"Folder not found: '{p}'."
        if not p.is_dir():
            return f"'{p}' is not a folder. Use delete_file to remove files."
        if recursive:
            shutil.rmtree(str(p))
            return f"Folder and all contents deleted: '{p}'."
        else:
            try:
                p.rmdir()
                return f"Empty folder deleted: '{p}'."
            except OSError:
                item_count = sum(1 for _ in p.iterdir())
                return (
                    f"Folder '{p}' is not empty ({item_count} items). "
                    "Set recursive=true to delete non-empty folders (Tier 4 — requires double confirmation)."
                )
