# Windows OS MCP Integration — Implementation Plan

## Context

Anythink needs 10 new `BuiltinMCPServer` subclasses giving the AI audited, permission-controlled access to Windows OS capabilities: file management, Explorer, app launching, window control, process management, system info, settings, clipboard, screenshots, and notifications. All servers share three cross-cutting components (safety tier checker, path guard, audit log) and register through the existing `MCPManager.register_builtin()` pattern unchanged.

**Total scope:** 13 new files in `mcp/windows/` and `mcp/builtin/`; 3 modified files (`config/schema.py`, `app/context.py`, `commands/handlers.py`, `pyproject.toml`); 59 tools across 10 servers; 12+ test files.

---

## Key Patterns to Reuse

- **Server contract:** `BuiltinMCPServer` ABC in `mcp/builtin/base.py` — `list_tools() -> list[MCPTool]` and `async call_tool(name, arguments) -> MCPCallResult`. Follow `FilesystemServer` exactly (timing + try/except wrapping, `_dispatch()` internal router).
- **Registration:** `MCPManager(builtin_servers=[...])` in `app/context.py` lines ~117-124.
- **Config mutation:** `replace(ctx.config, field=val); ctx.config_manager.save(new_cfg); ctx.config = new_cfg` — used in 12+ places in `commands/handlers.py`.
- **Frozen tuple fields:** `AppConfig` is `frozen=True`; list config fields must be `tuple[str, ...]`, appended with `tuple + (item,)`.
- **Deferred imports:** Every Windows-only import goes inside the method body, wrapped in `try/except ImportError` returning a user-friendly `MCPCallResult(is_error=True, content="Run: pip install anythink[windows]")`.
- **Sub-command dispatch:** In `commands/handlers.py`, `_mcp()` splits args into `sub`/`rest` — add `elif sub == "windows": return await _mcp_windows(ctx, rest, state)`.

---

## Phase 1 — Config Schema + pyproject.toml

**Files to modify:**
- `config/schema.py` — append `# --- Windows MCP fields ---` block after V4 MMOS section with 10 new `AppConfig` fields:
  - `windows_enabled: bool = False`
  - `windows_gui_mode: bool = False`
  - `windows_allowed_paths: tuple[str, ...] = ()` ← guard populates defaults at init
  - `windows_blocked_paths: tuple[str, ...] = ()` ← guard populates defaults at init
  - `windows_blocked_apps: tuple[str, ...] = ("regedit.exe", "cmd.exe", "powershell.exe", "mmc.exe")`
  - `windows_audit_log_enabled: bool = True`
  - `windows_audit_log_path: str = ""`
  - `windows_screenshot_max_px: int = 1920`
  - `windows_notification_app_name: str = "Anythink"`
  - `windows_apps_cache_ttl_minutes: int = 60`
- `config/manager.py` — in `load()`: add `raw.get(field, default)` for all 10 fields; in `save()`: serialize tuples as lists; in `validate_config()`: range-check `windows_screenshot_max_px > 0` and `windows_apps_cache_ttl_minutes > 0`.
- `pyproject.toml` — add `[windows]` optional extra: `pywin32>=306`, `psutil>=5.9`, `pygetwindow>=0.0.9`, `pyautogui>=0.9.54`, `Pillow>=10.0`, `winotify>=1.1.0`, `win10toast>=0.9`; append all 7 to the `all` extra list.

**Tests:** Extend `tests/test_config/` — test that loading old config without `windows_*` keys returns correct defaults; test `dataclasses.replace()` on new fields.

---

## Phase 2 — Cross-Cutting Infrastructure (`mcp/windows/` Package)

**Files to create:**
- `mcp/windows/__init__.py` — package marker, re-exports: `WindowsAuditLog`, `WindowsPathGuard`, `WindowsSafetyChecker`

- `mcp/windows/audit.py` — `WindowsAuditLog`:
  - `__init__(log_path: str)`: `logging.handlers.RotatingFileHandler(maxBytes=10MB, backupCount=5)`, JSONL output
  - `log(session_id, server, tool, tier, arguments, confirmation_status, outcome, duration_s, error)`: writes one JSON line per call
  - `get_recent(n, tool_filter=None, date_filter=None) -> list[dict]`: reads lines in reverse, parses JSON, filters
  - `export_to_text(output_path)`: formatted table to file
  - `clear()`: close handler → truncate → re-open

- `mcp/windows/paths.py` — `WindowsPathGuard`:
  - `__init__(config: AppConfig)`: loads `_allowed`/`_blocked` from config; `_NON_REMOVABLE_BLOCKED` = frozenset of system paths (C:\Windows\, System32\, Program Files\, etc.)
  - `validate(path: str) -> str | None`: `os.path.normcase(os.path.abspath(path))` → blocked prefix match (returns error) → allowed prefix match (returns None) → else error
  - `add_allowed`, `remove_allowed`, `add_blocked`, `remove_blocked`: mutate runtime state; callers persist via config replace

- `mcp/windows/safety.py` — `WindowsSafetyChecker`:
  - Module-level `_STATIC_TIERS: dict[str, dict[str, int]]` — maps all 59 tool names to tiers
  - `get_tier(server_name, tool_name, **kwargs) -> int`: static lookup + dynamic overrides: `write_file` → T2 if `not os.path.exists(path)` else T3; `delete_folder` → T4 if `recursive=True` else T3
  - `build_confirmation_prompt(tier, operation, server, target, consequence) -> str`: Rich-formatted box
  - `is_auto_allowed(tier) -> bool` (tier == 1)
  - `requires_double_confirm(tier) -> bool` (tier >= 4)

**Tests:** `tests/test_mcp/test_windows_infra.py` — test path normalization/traversal bypass prevention; tier resolution for all boundary cases; audit JSONL format; `get_recent` filters.

---

## Phase 3 — Read-Only / Low-Risk Servers

**Files to create:** `mcp/builtin/windows_system.py`, `mcp/builtin/windows_clipboard.py`, `mcp/builtin/windows_process.py`

**WindowsSystemServer** (`name = "windows-system"`):
- Constructor: `(audit: WindowsAuditLog)` — no safety needed (all Tier 1)
- 8 tools — all deferred deps (`psutil`, `platform`, `winreg`, `wmi`)
- `get_installed_apps`: quick winreg read (not the full cached discovery of AppsServer)

**WindowsClipboardServer** (`name = "windows-clipboard"`):
- Constructor: `(safety, audit)`
- `read_clipboard` (T1): `win32clipboard.OpenClipboard/GetClipboardData/CloseClipboard` in try/finally
- `write_clipboard` (T2): 1 MB cap (`len(text.encode("utf-16-le")) > 1_048_576`); audit logs first 100 chars
- `clear_clipboard` (T2): `win32clipboard.EmptyClipboard()`

**WindowsProcessServer** (`name = "windows-process"`):
- Constructor: `(safety, audit)`
- `list_processes` (T1): `psutil.process_iter(...)`, sorted by CPU%, formatted table
- `get_process_info` (T1): `psutil.Process(pid)`, catch `psutil.NoSuchProcess`
- `start_process` (T2): check against `config.windows_blocked_apps`, `subprocess.Popen`, return PID
- `kill_process` (T3): protect processes owned by `NT AUTHORITY\SYSTEM/LOCAL SERVICE/NETWORK SERVICE`; SIGTERM → 5s wait → SIGKILL if `force=True`

**Tests:** `test_windows_system.py`, `test_windows_clipboard.py`, `test_windows_process.py` — mock `sys.modules` for Windows deps; test tool listing + key success/error paths.

---

## Phase 4 — Settings & Notification Servers

**Files to create:** `mcp/builtin/windows_settings.py`, `mcp/builtin/windows_notification.py`

**WindowsSettingsServer** (`name = "windows-settings"`):
- Constructor: `(safety, audit)`
- Read (T1): `get_volume` via Core Audio COM (`comtypes`); `get_brightness` via WMI; `get_power_plan`/`list_power_plans` via `powercfg /list`; `get_timezone` via `tzutil /g`; `get_display_info` via `wmic`
- Write (T3): `set_volume` via `IAudioEndpointVolume`; `set_brightness` via `WmiMonitorBrightnessMethods`; `mute_audio` toggle; `set_power_plan` via `powercfg /s <GUID>`; `set_timezone` via `win32api.SetTimeZoneInformation` (returns clear error if not admin)

**WindowsNotificationServer** (`name = "windows-notification"`):
- Constructor: `(safety, audit)`
- `_scheduled: dict[str, asyncio.Task]` — in-process state
- `send_notification` (T2): `winotify.Notification(...).show()` preferred; `win10toast.ToastNotifier` fallback
- `send_scheduled_notification` (T2): parse `delay_seconds` or `at_time` string; `asyncio.get_event_loop().create_task(...)`, UUID key
- `list_scheduled_notifications` (T1): formatted table from `self._scheduled`
- `cancel_scheduled_notification` (T2): `task.cancel()`

**Tests:** Mock `subprocess.run` for powercfg output; test `set_timezone` returns error on `PermissionError`; mock `winotify`; test asyncio task creation/cancellation.

---

## Phase 5 — Window & Explorer Servers

**Files to create:** `mcp/builtin/windows_window.py`, `mcp/builtin/windows_explorer.py`

**WindowsWindowServer** (`name = "windows-window"`):
- Constructor: `(safety, audit, gui_mode: bool)`
- `_find_window(title)`: `pygetwindow.getWindowsWithTitle(title)` → fuzzy fallback via `getAllWindows()`
- T1: `list_open_windows` — `pygetwindow.getAllWindows()`, formatted table
- T2: `bring_to_foreground`, `minimize_window`, `maximize_window`, `restore_window` — pygetwindow methods
- T3: `close_window` — `win32api.SendMessage(hwnd, WM_CLOSE, 0, 0)` (deferred `win32api`/`win32con`)
- T3 + GUI-only gate: `send_text_to_window` — `pyautogui.typewrite(text, interval=0.05)`; return error if not `gui_mode`

**WindowsExplorerServer** (`name = "windows-explorer"`):
- Constructor: `(path_guard, safety, audit)`
- T2: `open_folder_in_explorer` — validate path → `subprocess.Popen(["explorer.exe", path])`
- T2: `open_file_with_default_app` — validate path → `os.startfile(path)`
- T2: `select_files_in_explorer` — `win32com.shell.shell.SHOpenFolderAndSelectItems`; fallback `/select,` flag
- T2: `navigate_explorer_to_path` — open new Explorer window at path (headless fallback)

**Tests:** Mock `pygetwindow`, `pyautogui`, `os.startfile`, `subprocess.Popen`; test path guard rejection; test GUI-mode gate on `send_text_to_window`.

---

## Phase 6 — Apps, Screenshot, Filesystem Servers

**Files to create:** `mcp/builtin/windows_apps.py`, `mcp/builtin/windows_screenshot.py`, `mcp/builtin/windows_filesystem.py`

**WindowsAppsServer** (`name = "windows-apps"`):
- Constructor: `(safety, audit, config: AppConfig)` — stores config for TTL and blocked_apps
- `_cache: list[dict] | None = None`, `_cache_time: float = 0.0`
- `list_installed_apps` (T1): TTL check; discover from: (a) `winreg HKLM Uninstall`, (b) `HKCU Uninstall`, (c) WOW6432Node, (d) Start Menu `.lnk` resolution; deduplicate; store in `_cache`
- `launch_app` (T2): `difflib.get_close_matches(name, app_names, n=3, cutoff=0.6)`; if 1 match → launch; if multiple → return list for user to confirm; check against `config.windows_blocked_apps`; `subprocess.Popen([executable] + args)`

**WindowsScreenshotServer** (`name = "windows-screenshot"`):
- Constructor: `(safety, audit, vision_capable: bool)`
- `take_screenshot` (T2, GUI-only): `PIL.ImageGrab.grab()` → auto-scale if `width > windows_screenshot_max_px` → if `vision_capable`: base64 encode + return `[IMAGE_BASE64]<data>` prefix; else: `pytesseract.image_to_string()` fallback
- `take_window_screenshot` (T2, GUI-only): pygetwindow bbox → `ImageGrab.grab(bbox=...)`
- `save_screenshot` (T2, works headless): validate path via path_guard → `img.save(path)` 

**WindowsFilesystemServer** (`name = "windows-filesystem"`):
- Constructor: `(path_guard, safety, audit)` — all 13 tools run `path_guard.validate()` first
- T1: `list_dir`, `read_file`, `get_file_metadata`, `search_files_by_name`, `search_files_by_content`
- T2 or T3: `write_file` (T2 new, T3 overwrite), `create_file`, `create_folder`, `copy_file` (T2 new dest, T3 overwrite)
- T3: `move_file`, `rename_file`, `delete_file`
- T3 or T4: `delete_folder` (T3 empty, T4 if `recursive=True`)
- `write_file`: enforce 10 MB cap
- `search_files_by_name`: `os.walk()` + `fnmatch.fnmatch()`, depth-limited to 5, max 200 results

**Tests:** Mock path guard to return `None`/error; test all 13 tools; test dynamic tier for `write_file`/`delete_folder`; test write cap; test TTL cache in AppsServer; test vision vs OCR branching in ScreenshotServer.

---

## Phase 7 — AppContext Registration

**File to modify:** `app/context.py`

Add module-level factory function (before `AppContext` class):
```python
def _build_windows_servers(config: AppConfig, paths: Paths) -> list[BuiltinMCPServer]:
    import sys
    if sys.platform != "win32" or not config.windows_enabled:
        return []
    # All 10 imports deferred here
    audit_path = config.windows_audit_log_path or str(paths.state_dir / "logs" / "windows_audit.log")
    path_guard = WindowsPathGuard(config)
    safety = WindowsSafetyChecker()
    audit = WindowsAuditLog(audit_path)
    vision_capable = _check_vision_capable(config)
    return [WindowsFilesystemServer(...), ..., WindowsNotificationServer(safety, audit)]
```

Add `_check_vision_capable(config) -> bool`: checks `config.default_model_alias` against known vision-capable model IDs; returns `False` if unclear.

In `AppContext.create()`: extend `builtin_servers` list with `*_build_windows_servers(config, resolved)`.

**Tests:** Extend `tests/test_app/test_context.py` — test factory returns `[]` on non-Windows / disabled; test returns 10 instances when enabled on Windows (mock all imports).

---

## Phase 8 — `/mcp windows` Command Namespace

**File to modify:** `commands/handlers.py`

In `_mcp()`, add `elif sub == "windows": return await _mcp_windows(ctx, rest, state)`.
Update usage string to include `|windows`.

Add `async def _mcp_windows(ctx, rest, state) -> CommandResult`:

| Sub-command | Behavior |
|---|---|
| `""` / `"status"` | Show all 10 Windows servers: name, tool count, enabled/disabled, last audit entry |
| `"mode gui"` / `"mode headless"` | `replace(ctx.config, windows_gui_mode=True/False)`, save |
| `"paths list"` | Show `_allowed` and `_blocked` from `WindowsPathGuard` |
| `"paths allow <path>"` | Update allowed list → persist via config replace |
| `"paths remove <path>"` | Remove from allowed list |
| `"paths block <path>"` / `"paths unblock <path>"` | Manage blocked list (non-removable system paths rejected) |
| `"apps"` | `await ctx.mcp_manager.call_tool("list_installed_apps", {})` |
| `"apps refresh"` | Access `WindowsAppsServer._cache = None` via `_builtins["windows-apps"]` |
| `"apps block <name>"` / `"apps unblock <name>"` | Update `windows_blocked_apps` tuple, save |
| `"audit"` / `"audit --n N"` / `"audit --tool T"` / `"audit --date today"` | `audit.get_recent(...)` |
| `"audit --export"` | `audit.export_to_text(export_path)` |
| `"audit clear"` | Return `CommandResult(action="windows_audit_clear_confirm")` |
| `"screenshot"` | Return `CommandResult(action="mcp_call_request", extra={"tool": "take_screenshot"})` |
| `"clip read"` | `await ctx.mcp_manager.call_tool("read_clipboard", {})` |
| `"clip write <text>"` | `await ctx.mcp_manager.call_tool("write_clipboard", {"text": text})` |
| `"notify <message>"` | `await ctx.mcp_manager.call_tool("send_notification", {"title": "Anythink", "message": msg})` |

Path guard/audit accessed via `ctx.mcp_manager._builtins.get("windows-filesystem")._path_guard` etc.

**Tests:** `tests/test_mcp/test_windows_handler.py` — test all sub-commands produce correct `CommandResult` shapes; test `clip read` invokes correct tool; test `mode gui` updates config.

---

## Phase 9 — Entry Points + Final Package Wiring

**File to modify:** `pyproject.toml` — add 10 entries under `[project.entry-points."anythink.mcp_servers"]`:
```toml
windows_filesystem = "anythink.mcp.builtin.windows_filesystem:WindowsFilesystemServer"
# ... all 10
```
Note: Entry-point registration is harmless on non-Windows; `_build_windows_servers()` is the actual guard.

Confirm `mcp/windows/__init__.py` re-exports all three infrastructure classes.

After this phase: run `pip install -e .` to re-register entry points.

---

## Phase 10 — Integration Tests & Tool Count Verification

**Files to create:** `tests/test_mcp/test_windows_integration.py`

Key integration tests:
- `test_all_59_tool_names_unique()`: Instantiate all 10 servers with mocked deps; collect all tool names from `list_tools()`; assert no duplicates, assert count == 59
- `test_mcp_manager_indexes_all_tools()`: Pass all 10 to `MCPManager`; assert all 59 tools routable
- `test_platform_guard_returns_empty_on_linux()`: `patch("sys.platform", "linux")` → `_build_windows_servers(cfg, paths)` → assert `[]`
- `test_audit_log_written_on_call()`: Real `WindowsAuditLog` with `tmp_path`; call one tool; assert JSONL line written

**Final CI verification:**
```
ruff check src/
black --check src/ tests/
mypy src/anythink
bandit -r src/anythink -c pyproject.toml
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/test_mcp/ tests/test_config/ -v
```

On Windows with `pip install anythink[windows]`: start Anythink → `/mcp windows status` → verify all 10 servers listed → test each tool group.

---

## File Structure Summary

```
src/anythink/mcp/
├── windows/                          NEW PACKAGE
│   ├── __init__.py
│   ├── safety.py                     WindowsSafetyChecker
│   ├── paths.py                      WindowsPathGuard
│   └── audit.py                      WindowsAuditLog
└── builtin/
    ├── windows_filesystem.py         13 tools
    ├── windows_explorer.py           4 tools
    ├── windows_apps.py               2 tools
    ├── windows_window.py             7 tools
    ├── windows_process.py            4 tools
    ├── windows_system.py             8 tools
    ├── windows_settings.py           11 tools
    ├── windows_clipboard.py          3 tools
    ├── windows_screenshot.py         3 tools
    └── windows_notification.py       4 tools    (Total: 59 tools)

Modified:
  config/schema.py           10 new AppConfig fields
  config/manager.py          load/save/validate for new fields
  app/context.py             _build_windows_servers() factory + registration
  commands/handlers.py       /mcp windows sub-namespace
  pyproject.toml             [windows] extra + entry points
```

## Phase Dependency Order

Phases 1 → 2 → 3,4,5,6 (parallel) → 7 → 8 → 9 → 10

---

*First action on implementation start: create `windows_mcp_plan.md` in project root as a copy of this plan.*
