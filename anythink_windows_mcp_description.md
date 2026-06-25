# Anythink — Windows OS MCP Integration Build

> Ten new `BuiltinMCPServer` subclasses extend Anythink's MCP layer to give the
> AI direct, audited, permission-controlled access to the Windows operating system
> — from file management and application launching to window control, system
> settings, clipboard, screenshots, and desktop notifications. Every operation is
> classified into a four-tier safety system. Every action is written to a
> persistent audit log. All ten servers register through the existing
> `MCPManager.register_builtin()` pattern with zero changes to core MCP
> architecture.

---

## Table of Contents

1. [Overview & Design Philosophy](#1-overview--design-philosophy)
2. [New File Structure](#2-new-file-structure)
3. [Four-Tier Safety System](#3-four-tier-safety-system)
4. [Path Permission System](#4-path-permission-system)
5. [Windows Audit Log](#5-windows-audit-log)
6. [WindowsFilesystemServer](#6-windowsfilesystemserver)
7. [WindowsExplorerServer](#7-windowsexplorerserver)
8. [WindowsAppsServer](#8-windowsappsserver)
9. [WindowsWindowServer](#9-windowswindowserver)
10. [WindowsProcessServer](#10-windowsprocessserver)
11. [WindowsSystemServer](#11-windowssystemserver)
12. [WindowsSettingsServer](#12-windowssettingsserver)
13. [WindowsClipboardServer](#13-windowsclipboardserver)
14. [WindowsScreenshotServer](#14-windowsscreenshotserver)
15. [WindowsNotificationServer](#15-windowsnotificationserver)
16. [Headless vs GUI Mode](#16-headless-vs-gui-mode)
17. [Python Dependencies](#17-python-dependencies)
18. [AppConfig Changes](#18-appconfig-changes)
19. [The `/mcp windows` Command Namespace](#19-the-mcp-windows-command-namespace)
20. [Registration in AppContext](#20-registration-in-appcontext)
21. [Architecture Changes Summary](#21-architecture-changes-summary)

---

## 1. Overview & Design Philosophy

### 1.1 What This Build Adds

This build extends Anythink's existing MCP infrastructure with ten new
`BuiltinMCPServer` subclasses, each owning a distinct Windows OS capability
domain. Together they allow the AI — when the user has enabled the relevant
servers — to operate directly within the Windows environment: managing files,
opening applications, controlling windows, reading system state, adjusting
system settings, reading and writing the clipboard, capturing screenshots
as conversation context, and sending desktop notifications.

### 1.2 What Does Not Change

The entire existing MCP architecture remains unchanged:

- `MCPManager`, its `_tool_index`, and `call_tool()` dispatch are untouched
- `MCPConnectConfig`, `MCPTool`, `MCPCallResult`, `MCPServerInfo` models are untouched
- All four existing built-in servers (`FilesystemServer`, `RAGServer`,
  `SearchServer`, `SessionsServer`) remain unchanged
- `MCPClient`, `AnythinkMCPServer`, and all external connection logic are untouched
- The `/mcp` command namespace and TUI workers are extended, not replaced

### 1.3 How the New Servers Fit Into the Existing Architecture

Each new server follows the exact pattern documented in the existing
`builtin/base.py` contract: subclass `BuiltinMCPServer`, set `name` and
`description`, implement `list_tools()` and `async call_tool()`. They are
registered at startup via `MCPManager.register_builtin()` exactly like the
existing four servers.

The new servers share three cross-cutting components — the safety tier
checker, the path permission validator, and the audit logger — which are
instantiated once and injected into every server that needs them.

### 1.4 Windows-Only Guard

All ten new servers detect at startup whether they are running on Windows
(`sys.platform == "win32"`). On non-Windows platforms, they register
normally but every tool call returns an immediate, clear error:
`"This tool requires Windows. Current platform: <sys.platform>"`. This
ensures the servers can be imported and registered cross-platform without
breaking, even though they only function on Windows.

---

## 2. New File Structure

```
src/anythink/mcp/
├── __init__.py                   (unchanged)
├── models.py                     (unchanged)
├── manager.py                    (unchanged)
├── client.py                     (unchanged)
├── server.py                     (unchanged)
│
├── builtin/
│   ├── __init__.py               (unchanged)
│   ├── base.py                   (unchanged)
│   ├── filesystem.py             (unchanged — original cross-platform server)
│   ├── rag.py                    (unchanged)
│   ├── search.py                 (unchanged)
│   ├── sessions.py               (unchanged)
│   │
│   │   ── NEW ──────────────────────────────────────────────────────
│   ├── windows_filesystem.py     WindowsFilesystemServer
│   ├── windows_explorer.py       WindowsExplorerServer
│   ├── windows_apps.py           WindowsAppsServer
│   ├── windows_window.py         WindowsWindowServer
│   ├── windows_process.py        WindowsProcessServer
│   ├── windows_system.py         WindowsSystemServer
│   ├── windows_settings.py       WindowsSettingsServer
│   ├── windows_clipboard.py      WindowsClipboardServer
│   ├── windows_screenshot.py     WindowsScreenshotServer
│   └── windows_notification.py   WindowsNotificationServer
│
└── windows/                      ── NEW cross-cutting components ───
    ├── __init__.py
    ├── safety.py                 WindowsSafetyChecker — tier classification
    ├── paths.py                  WindowsPathGuard — allowed/blocked paths
    └── audit.py                  WindowsAuditLog — persistent action log
```

---

## 3. Four-Tier Safety System

### 3.1 What It Is

Every tool call made by any of the ten new Windows servers is classified into
one of four safety tiers before execution. The tier determines whether the
operation proceeds automatically, follows the existing autonomy mode, requires
explicit user confirmation, or requires double confirmation. This is enforced
by `WindowsSafetyChecker` in `windows/safety.py`, which is instantiated once
and injected into every server that needs it.

### 3.2 The Four Tiers

**Tier 1 — Auto-Allowed (Read Only)**

Operations that only read state and cannot cause any data loss or system change.
These proceed immediately without any confirmation or autonomy check.

Examples: `list_dir`, `read_file`, `get_file_metadata`, `search_files_by_name`,
`search_files_by_content`, `list_open_windows`, `list_processes`,
`get_cpu_usage`, `get_ram_usage`, `get_disk_space`, `get_battery_status`,
`get_network_info`, `get_installed_apps`, `get_windows_version`,
`get_hardware_info`, `get_volume`, `get_brightness`, `get_power_plan`,
`get_timezone`, `read_clipboard`, `list_sessions`.

**Tier 2 — Autonomy Mode Applies**

Non-destructive write and launch operations. These follow the existing
`browse_autonomy` / `exec_mode` pattern — in `"auto"` mode they proceed
without asking; in `"ask"` mode they show a confirmation prompt first.

Examples: `write_file` (new file, no overwrite), `create_file`, `create_folder`,
`launch_app`, `start_process`, `open_folder_in_explorer`,
`navigate_explorer_to_path`, `open_file_with_default_app`,
`bring_window_to_foreground`, `minimize_window`, `maximize_window`,
`write_clipboard`, `send_notification`, `take_screenshot`.

**Tier 3 — Always Confirm**

Destructive or system-changing operations that always require explicit user
confirmation, regardless of the autonomy mode setting. Even in `"auto"` mode,
the system pauses and waits for the user to type `y` or `yes` before
proceeding.

Examples: `delete_file`, `delete_folder`, `copy_file` (overwrite),
`move_file` (overwrite), `rename_file` (overwrite), `write_file` (overwrite
existing), `kill_process`, `close_window`, `send_text_to_window`,
`set_volume`, `set_brightness`, `set_power_plan`, `set_timezone`.

**Tier 4 — Double Confirm**

The most dangerous operations — those targeting system-critical paths, the
Windows Registry, or involving cascading system state changes. These require
confirmation twice: first when the AI announces its intent, and again with
the exact operation details just before execution.

Examples: Any Tier 3 operation targeting a system-critical path (see Section 4),
any operation that would affect running system processes that are not user-owned,
any bulk delete operation covering more than 10 files.

### 3.3 Confirmation Prompt Format

Tier 3 confirmations use a structured, clearly labeled prompt in the chat
interface so the user understands exactly what is about to happen:

```
╭─ ⚠ Confirmation Required — Tier 3 Operation ──────────────────────╮
│                                                                     │
│  Operation:    delete_file                                          │
│  Server:       windows-filesystem                                  │
│  Target:       C:\Users\MD\Documents\old_config.json               │
│  Consequence:  This file will be permanently deleted.              │
│                                                                     │
│  Type "yes" to confirm or "no" to cancel:  _                      │
╰─────────────────────────────────────────────────────────────────────╯
```

Tier 4 shows the same prompt twice, with the second prompt rephrasing to
confirm the user has read the full operation details:

```
╭─ ⚠ Second Confirmation — High-Risk Operation ──────────────────────╮
│                                                                     │
│  You are about to permanently delete 15 files.                     │
│  This cannot be undone. Confirm again to proceed.                  │
│                                                                     │
│  Type "confirm" to proceed:  _                                     │
╰─────────────────────────────────────────────────────────────────────╯
```

### 3.4 Tier Classification is Static

Each tool is assigned to exactly one tier, defined at the server level as a
class-level constant mapping tool names to their tier numbers. The tier cannot
be changed by the user, and the AI cannot request a tier downgrade. A Tier 3
operation is always Tier 3.

---

## 4. Path Permission System

### 4.1 What It Is

`WindowsPathGuard` in `windows/paths.py` is the single gatekeeper for all
filesystem operations. Before any file or folder operation executes, the target
path is validated against two lists: the allowed paths list and the blocked
paths list. Any path that fails validation causes the tool call to return an
immediate `MCPCallResult(is_error=True)` with a descriptive message — no
confirmation prompt is shown because the operation is simply not permitted.

### 4.2 Allowed Paths — User-Configured Whitelist

The AI can only operate on files and folders within the user-configured allowed
paths list. Operations targeting any path outside this list are rejected, even
if that path is not explicitly blocked.

Default allowed paths (configurable in `/settings` → Windows → Allowed paths):

- `C:\Users\<current_user>\Documents\`
- `C:\Users\<current_user>\Desktop\`
- `C:\Users\<current_user>\Downloads\`

The user can add additional paths (e.g., a project directory like
`D:\Projects\`) and remove default paths via:

```
/mcp windows paths allow C:\MyProject\
/mcp windows paths allow D:\Data\
/mcp windows paths list
/mcp windows paths remove C:\Users\MD\Downloads\
```

### 4.3 Blocked Paths — System-Critical Blacklist

Certain paths are always blocked regardless of the allowed paths list. These
are paths where AI-driven modifications could damage the Windows installation,
corrupt system state, or create security vulnerabilities. Blocked paths are
applied as prefix matches — any path beginning with a blocked prefix is rejected.

**Default blocked paths (non-removable):**

```
C:\Windows\
C:\Windows\System32\
C:\Windows\SysWOW64\
C:\Program Files\
C:\Program Files (x86)\
C:\ProgramData\Microsoft\
C:\Users\<current_user>\AppData\Roaming\
C:\Users\<current_user>\AppData\Local\Microsoft\
<Anythink installation directory>\
```

**User-configurable additional blocked paths:**

The user can add their own blocked paths (paths they want to protect from
AI access even if they fall within an allowed parent directory):

```
/mcp windows paths block C:\Users\MD\Documents\Private\
/mcp windows paths block D:\Sensitive\
/mcp windows paths blocked    ← list all blocked paths
```

Blocked paths take priority over allowed paths. If a path is in both lists,
it is always blocked.

### 4.4 Path Normalization

Before validation, all paths are normalized: resolved to absolute paths,
lowercased for comparison (Windows paths are case-insensitive), and any `..`
traversal segments are resolved. This prevents path traversal bypass attempts
such as `C:\Users\MD\Documents\..\AppData\`.

---

## 5. Windows Audit Log

### 5.1 What Is Logged

Every tool call made through any of the ten Windows servers — regardless of
whether it succeeds, fails, is confirmed, or is cancelled — is written as a
structured JSON record to the Windows audit log. This provides a permanent,
searchable, human-readable record of every action the AI has taken on the
Windows system.

### 5.2 Log Location

```
$XDG_STATE_HOME\anythink\logs\windows_audit.log
```

(Defaults to `%LOCALAPPDATA%\anythink\logs\windows_audit.log` on Windows when
XDG is not configured.)

The log file uses rolling rotation — when it reaches 10 MB, it is renamed
to `windows_audit.1.log` and a fresh file begins. Up to 5 rotated files are
retained (50 MB total log history).

### 5.3 Log Record Format

Each log entry is a single JSON object per line (JSONL format):

```json
{
  "timestamp": "2025-06-18T14:32:11.421Z",
  "session_id": "a1b2c3d4",
  "server": "windows-filesystem",
  "tool": "delete_file",
  "tier": 3,
  "arguments": {
    "path": "C:\\Users\\MD\\Documents\\old_config.json"
  },
  "confirmation_status": "confirmed",
  "outcome": "success",
  "duration_s": 0.012,
  "error": null
}
```

| Field | Description |
|---|---|
| `timestamp` | ISO 8601 UTC timestamp |
| `session_id` | The Anythink session ID this action occurred in |
| `server` | Which Windows server handled the call |
| `tool` | The specific tool that was called |
| `tier` | The safety tier (1–4) |
| `arguments` | The exact arguments passed to the tool (paths, names, values) |
| `confirmation_status` | `"not_required"`, `"confirmed"`, `"cancelled"`, `"auto"` |
| `outcome` | `"success"`, `"error"`, `"blocked_by_path_guard"`, `"cancelled_by_user"` |
| `duration_s` | Wall-clock execution time |
| `error` | Error message if outcome is not success, else null |

### 5.4 Viewing the Audit Log

```
/mcp windows audit              Show last 20 audit entries in the chat
/mcp windows audit --n 50       Show last 50 entries
/mcp windows audit --tool delete_file    Filter by tool name
/mcp windows audit --date today Show only today's entries
/mcp windows audit --export     Export full log to a formatted text file
```

---

## 6. WindowsFilesystemServer

**File:** `builtin/windows_filesystem.py`
**Name:** `"windows-filesystem"`
**Description:** `"Full file and folder management on Windows within allowed paths."`

### 6.1 Injected Dependencies

```python
WindowsFilesystemServer(
    path_guard: WindowsPathGuard,
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 6.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `list_dir` | 1 | List contents of a directory with names, types, and sizes |
| `read_file` | 1 | Read the text content of a file |
| `get_file_metadata` | 1 | Get size, creation date, modified date, and permissions for a file or folder |
| `search_files_by_name` | 1 | Recursively search for files matching a name pattern |
| `search_files_by_content` | 1 | Search files containing a specific text string |
| `write_file` | 2 or 3 | Write text content to a file (Tier 2 if new, Tier 3 if overwrite) |
| `create_file` | 2 | Create a new empty file at the specified path |
| `create_folder` | 2 | Create a new folder (including all intermediate directories) |
| `copy_file` | 2 or 3 | Copy a file to a destination (Tier 2 if destination is new, Tier 3 if overwrite) |
| `move_file` | 3 | Move a file or folder to a new location |
| `rename_file` | 3 | Rename a file or folder |
| `delete_file` | 3 | Permanently delete a file |
| `delete_folder` | 3 or 4 | Delete a folder (Tier 3 if empty, Tier 4 if recursive non-empty) |

### 6.3 Tool Argument Schemas

**`list_dir`** — `path: str`, `show_hidden: bool = False`

**`read_file`** — `path: str`, `encoding: str = "utf-8"`

**`get_file_metadata`** — `path: str`

**`search_files_by_name`** — `root_path: str`, `pattern: str`, `recursive: bool = True`
Pattern supports `*` (any characters) and `?` (single character). Example:
`*.py`, `config*.json`.

**`search_files_by_content`** — `root_path: str`, `query: str`, `file_extensions: list[str] | None = None`, `recursive: bool = True`
Content search reads each file and checks for the presence of `query` as a
substring (case-insensitive). Supports `.txt`, `.md`, `.py`, `.json`, `.yaml`,
`.csv`, `.log` and other text-readable formats. Binary files are skipped.

**`write_file`** — `path: str`, `content: str`, `encoding: str = "utf-8"`, `overwrite: bool = False`
`overwrite=True` escalates to Tier 3 and requires confirmation.

**`create_file`** — `path: str`

**`create_folder`** — `path: str`, `exist_ok: bool = True`

**`copy_file`** — `source: str`, `destination: str`, `overwrite: bool = False`

**`move_file`** — `source: str`, `destination: str`

**`rename_file`** — `path: str`, `new_name: str`
`new_name` is just the filename, not a full path. The file stays in its
current directory.

**`delete_file`** — `path: str`

**`delete_folder`** — `path: str`, `recursive: bool = False`
`recursive=True` (delete non-empty folder) escalates to Tier 4.

### 6.4 `list_dir` Output Format

```
C:\Users\MD\Documents\  (12 items)
─────────────────────────────────────────────
📁  Projects\              [folder]  —
📁  Reports\               [folder]  —
📄  budget.xlsx            [file]    42 KB  modified 2 days ago
📄  notes.md               [file]    8 KB   modified just now
📄  old_config.json        [file]    1 KB   modified 6 months ago
```

### 6.5 `get_file_metadata` Output Format

```
Path:          C:\Users\MD\Documents\notes.md
Type:          File
Size:          8,192 bytes (8 KB)
Created:       2025-01-14 09:30:22
Modified:      2025-06-18 14:22:01
Accessed:      2025-06-18 14:22:01
Permissions:   Read ✓  Write ✓  Execute ✗
Owner:         MD\Users
```

---

## 7. WindowsExplorerServer

**File:** `builtin/windows_explorer.py`
**Name:** `"windows-explorer"`
**Description:** `"Open and navigate Windows File Explorer; open files with their default applications."`

### 7.1 Injected Dependencies

```python
WindowsExplorerServer(
    path_guard: WindowsPathGuard,
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 7.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `open_folder_in_explorer` | 2 | Open a folder in a new File Explorer window |
| `navigate_explorer_to_path` | 2 | Navigate an already-open File Explorer window to a specific path |
| `open_file_with_default_app` | 2 | Open a file using its associated default application |
| `select_files_in_explorer` | 2 | Open a File Explorer window with specific files pre-selected |

### 7.3 Tool Argument Schemas

**`open_folder_in_explorer`** — `path: str`
Opens a new File Explorer window showing the contents of `path`.
Uses `subprocess.Popen(["explorer.exe", path])`.

**`navigate_explorer_to_path`** — `path: str`, `window_title: str | None = None`
If `window_title` is given, navigates the File Explorer window whose title
matches to the new path using Win32 API SHBrowseForFolder automation via
`pywin32`. If no window is specified, opens a new Explorer window at `path`.

**`open_file_with_default_app`** — `path: str`
Uses `os.startfile(path)` which invokes Windows' ShellExecute with the
`"open"` verb, opening the file in whatever application is registered as
the default for that file type. This is equivalent to double-clicking a
file in File Explorer.

**`select_files_in_explorer`** — `paths: list[str]`
Opens a File Explorer window with the specified files highlighted/selected.
Uses the `SHOpenFolderAndSelectItems` Win32 API via `pywin32`. All files must
be in the same directory — if paths span multiple directories, multiple
Explorer windows are opened, one per directory.

---

## 8. WindowsAppsServer

**File:** `builtin/windows_apps.py`
**Name:** `"windows-apps"`
**Description:** `"Launch installed Windows applications by name."`

### 8.1 Injected Dependencies

```python
WindowsAppsServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 8.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `list_installed_apps` | 1 | List all installed applications discoverable on this system |
| `launch_app` | 2 | Launch an installed application by name or executable |

### 8.3 `list_installed_apps` — How Apps Are Discovered

Installed applications are discovered from four sources, merged and
deduplicated:

1. **Windows Registry — HKEY_LOCAL_MACHINE Uninstall:** All entries under
   `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall` and the WOW6432Node
   equivalent. This covers most MSI-installed applications.
2. **Windows Registry — HKEY_CURRENT_USER Uninstall:** User-scope installed
   applications.
3. **Start Menu shortcuts:** `.lnk` files in
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\` and
   `%ProgramData%\Microsoft\Windows\Start Menu\Programs\`, resolved to their
   target executables.
4. **PATH environment variable:** All executables found in `%PATH%` directories.

The result is a list of application names with their resolved executable paths.
This list is cached in memory for the session — it is expensive to build and
changes rarely. `/mcp windows apps refresh` forces a cache rebuild.

**Output format:**

```
Installed Applications (143 found)
─────────────────────────────────────────────────────────
Notepad             C:\Windows\System32\notepad.exe
Visual Studio Code  C:\Users\MD\AppData\Local\Programs\Microsoft VS Code\Code.exe
Google Chrome       C:\Program Files\Google\Chrome\Application\chrome.exe
Python 3.12         C:\Users\MD\AppData\Local\Programs\Python\Python312\python.exe
...
```

### 8.4 `launch_app` — Fuzzy Name Matching

`launch_app` accepts a `name: str` parameter. This name is matched against
the discovered app list using a fuzzy match algorithm — so "vs code", "vscode",
"visual studio code" all resolve to the same application. If multiple
applications match the name, Anythink shows the top 3 matches and asks the
user to confirm which one to launch before proceeding.

**Argument schema:** `name: str`, `args: list[str] = []`

`args` are additional command-line arguments passed to the launched executable
(e.g., a file path for applications that accept one).

Applications on the default blocked-apps list (configurable in settings) can
never be launched via this tool, even if the AI requests them. The default
blocked-apps list includes: `regedit.exe`, `cmd.exe`, `powershell.exe`,
`mmc.exe` — tools that could be used for further privilege escalation.

---

## 9. WindowsWindowServer

**File:** `builtin/windows_window.py`
**Name:** `"windows-window"`
**Description:** `"List, focus, resize, and interact with open Windows application windows."`

### 9.1 Injected Dependencies

```python
WindowsWindowServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 9.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `list_open_windows` | 1 | List all currently visible application windows with titles and states |
| `bring_to_foreground` | 2 | Bring a specific window to the foreground and give it focus |
| `minimize_window` | 2 | Minimize a window to the taskbar |
| `maximize_window` | 2 | Maximize a window to fill the screen |
| `restore_window` | 2 | Restore a minimized or maximized window to its normal size |
| `close_window` | 3 | Close a window (sends WM_CLOSE — application may prompt to save) |
| `send_text_to_window` | 3 | Type text into the currently focused control of a window |

### 9.3 Window Identification

Windows are identified by their **title string** as it appears in the taskbar
and window title bar. Tool arguments that take a window reference accept a
`title: str` parameter and use fuzzy matching — partial, case-insensitive match
against all open window titles. If multiple windows match, the best match is
used and the match is reported in the result so the user can verify.

**`list_open_windows`** output format:

```
Open Windows (11 windows)
─────────────────────────────────────────────────────
  ID    Title                                  State
─────────────────────────────────────────────────────
  0001  Anythink — terminal                    Normal
  0002  Visual Studio Code — my-project        Maximized
  0003  Google Chrome — GitHub                 Normal
  0004  File Explorer — Documents              Normal
  0005  Notepad — budget_notes.txt             Minimized
```

Window IDs are session-scoped integers assigned at list time — they are stable
for the duration of the tool call chain within one conversation turn but may
change between turns as windows open and close.

### 9.4 `send_text_to_window`

**Argument schema:** `title: str`, `text: str`, `press_enter: bool = False`

Sends `text` to the focused input control of the window matching `title` by
simulating keyboard input via `pyautogui.typewrite()` (with appropriate
interval between keystrokes to avoid input buffer overflow). If `press_enter`
is `True`, a Return keypress is sent after the text.

This tool is restricted by GUI mode — in headless mode it is unavailable (see
Section 16). It always requires Tier 3 confirmation since it sends keyboard
input to an external application on the user's behalf.

---

## 10. WindowsProcessServer

**File:** `builtin/windows_process.py`
**Name:** `"windows-process"`
**Description:** `"List, start, and stop Windows processes."`

### 10.1 Injected Dependencies

```python
WindowsProcessServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 10.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `list_processes` | 1 | List all running processes with PID, name, CPU%, and RAM usage |
| `get_process_info` | 1 | Get detailed info for a specific process by PID or name |
| `start_process` | 2 | Start a new process by executable path or command string |
| `kill_process` | 3 | Terminate a process by PID or name (graceful first, then force) |

### 10.3 `list_processes` — Using `psutil`

Lists all running processes using `psutil.process_iter()`. Returns a formatted
table sorted by CPU usage descending (most CPU-intensive first), matching the
presentation of Windows Task Manager:

```
Running Processes (247 processes)
─────────────────────────────────────────────────────────────────────
  PID    Name                    CPU%    RAM        Status
─────────────────────────────────────────────────────────────────────
  8844   chrome.exe              12.4%   512 MB     running
  4512   Code.exe                 8.1%   287 MB     running
 12044   python.exe               4.3%   143 MB     running
   892   explorer.exe             0.8%    62 MB     running
    ...
```

### 10.4 `start_process`

**Argument schema:** `command: str`, `args: list[str] = []`, `working_dir: str | None = None`, `detached: bool = True`

Launches a new process using `subprocess.Popen()`. `detached=True` (default)
runs the process independently of Anythink — it continues running after the
tool call completes. `detached=False` runs the process and waits for it to
complete, returning its stdout and stderr (capped at 5,000 characters total).

The `command` is the executable path or a command string. It goes through the
blocked-apps list check — the same list applied in `WindowsAppsServer.launch_app`.

Returns the new process's PID on success.

### 10.5 `kill_process`

**Argument schema:** `pid: int | None = None`, `name: str | None = None`, `force: bool = False`

Either `pid` or `name` must be provided. If `name` is given and multiple
processes match, all matching processes are shown and the user is asked to
confirm which to terminate.

Termination sequence:
1. Send `SIGTERM` (graceful termination request) via `psutil.Process.terminate()`
2. Wait up to 5 seconds for the process to exit
3. If still running and `force=True`: send `SIGKILL` (force kill) via
   `psutil.Process.kill()`
4. If still running and `force=False`: report that the process did not terminate
   gracefully and ask the user whether to force-kill

System-critical processes (any process owned by `SYSTEM`, `LOCAL SERVICE`,
or `NETWORK SERVICE` Windows accounts) are protected — attempts to kill them
are rejected with a clear explanation, even at Tier 3. This protection is
non-configurable.

---

## 11. WindowsSystemServer

**File:** `builtin/windows_system.py`
**Name:** `"windows-system"`
**Description:** `"Read system hardware and OS information: CPU, RAM, disk, network, battery, and installed software."`

### 11.1 Injected Dependencies

```python
WindowsSystemServer(audit: WindowsAuditLog)
```
No safety checker or path guard needed — all tools are Tier 1 read-only.

### 11.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `get_cpu_info` | 1 | CPU model, core count, current usage per core, and overall CPU% |
| `get_ram_info` | 1 | Total RAM, used RAM, free RAM, and usage percentage |
| `get_disk_info` | 1 | All drives with total, used, free space, and filesystem type |
| `get_battery_info` | 1 | Battery percentage, charging state, estimated time remaining |
| `get_network_info` | 1 | All network adapters with IP addresses, MAC addresses, and connection status |
| `get_windows_version` | 1 | Windows edition, version number, build number, and architecture |
| `get_hardware_info` | 1 | CPU model, RAM modules, motherboard, GPU(s), and BIOS version |
| `get_installed_apps` | 1 | Same as WindowsAppsServer's list — full installed application list |

### 11.3 Implementation Libraries

- `psutil` — `cpu_percent()`, `cpu_count()`, `virtual_memory()`, `disk_partitions()`, `disk_usage()`, `battery()`, `net_if_addrs()`, `net_if_stats()`
- `platform` (stdlib) — `platform.version()`, `platform.machine()`
- `pywin32` via `winreg` — hardware details from Windows registry (`HKLM\HARDWARE\DESCRIPTION\System\BIOS`, `HKLM\SYSTEM\CurrentControlSet\Enum`)
- `wmi` (optional, part of `pywin32`) — GPU information via WMI `Win32_VideoController`

### 11.4 Example Output — `get_cpu_info`

```
CPU Information
─────────────────────────────────────────────────────
Model:          Intel Core i7-12700H
Physical cores: 14 (20 logical)
Base speed:     2.3 GHz
Max speed:      4.7 GHz

Current Usage:
  Overall:  23.4%
  Core 0:   45.2%  Core 1:   12.1%  Core 2:   31.8%
  Core 3:    8.4%  Core 4:   19.3%  Core 5:    5.6%
  ...
```

---

## 12. WindowsSettingsServer

**File:** `builtin/windows_settings.py`
**Name:** `"windows-settings"`
**Description:** `"Read and change Windows system settings: volume, display brightness, power plan, and time zone."`

### 12.1 Injected Dependencies

```python
WindowsSettingsServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 12.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `get_volume` | 1 | Get current system volume level (0–100) and mute state |
| `set_volume` | 3 | Set system volume to a specific level (0–100) |
| `mute_audio` | 3 | Mute or unmute system audio |
| `get_brightness` | 1 | Get current display brightness (0–100) |
| `set_brightness` | 3 | Set display brightness to a specific level (0–100) |
| `get_power_plan` | 1 | Get current active power plan name |
| `list_power_plans` | 1 | List all available power plans |
| `set_power_plan` | 3 | Switch to a specified power plan |
| `get_timezone` | 1 | Get current system time zone |
| `set_timezone` | 3 | Change system time zone |
| `get_display_info` | 1 | Get display resolution, refresh rate, and scaling for all monitors |

### 12.3 Implementation Details

**Volume control:** Uses the Windows Core Audio API via `pywin32`'s
`comtypes` bindings to `IAudioEndpointVolume`. Volume is expressed as a
0–100 integer (mapped to the 0.0–1.0 float the API uses internally).

**Brightness control:** Uses the `WmiMonitorBrightnessMethods` WMI class via
`pywin32`'s WMI interface. Only works for built-in laptop displays and monitors
that expose WMI brightness control. External monitors connected via DisplayPort
or HDMI that do not support DDC/CI will return `"Brightness control not
supported for this display."` rather than an error.

**Power plans:** Uses `subprocess` to call `powercfg /list` (list plans),
`powercfg /getactivescheme` (get current), and `powercfg /setactive <guid>`
(switch plans). Power plan names are matched to GUIDs at call time.

**Time zone:** Uses `pywin32`'s `win32api.SetTimeZoneInformation()` for
setting and `time.tzname` / registry read for getting. Setting the time zone
requires Anythink to be running with administrator privileges — if not,
the tool returns a clear error explaining the privilege requirement.

---

## 13. WindowsClipboardServer

**File:** `builtin/windows_clipboard.py`
**Name:** `"windows-clipboard"`
**Description:** `"Read from and write to the Windows clipboard."`

### 13.1 Injected Dependencies

```python
WindowsClipboardServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 13.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `read_clipboard` | 1 | Read the current text content of the Windows clipboard |
| `write_clipboard` | 2 | Write text to the Windows clipboard, replacing current contents |
| `clear_clipboard` | 2 | Clear the clipboard contents |

### 13.3 Implementation

Uses `pywin32`'s `win32clipboard` module for all operations:
`OpenClipboard()`, `GetClipboardData(CF_UNICODETEXT)`, `SetClipboardData()`,
`EmptyClipboard()`, `CloseClipboard()` — always called in a try/finally block
to guarantee the clipboard is closed even on error.

`read_clipboard` returns text content only. Non-text clipboard content
(images, file references, rich text) returns a descriptive message indicating
the content type without attempting to convert it:
`"Clipboard contains an image (not text). Use /screenshot to capture screen content."`.

`write_clipboard` is capped at **1 MB of text** — larger content is rejected
with a size hint and a suggestion to write to a file instead.

When `write_clipboard` succeeds, the result includes a confirmation of what
was written: `"Clipboard updated: 347 characters written."` This is logged
to the audit log with the first 100 characters of the written text for
traceability.

---

## 14. WindowsScreenshotServer

**File:** `builtin/windows_screenshot.py`
**Name:** `"windows-screenshot"`
**Description:** `"Capture screenshots of the full screen or a specific window and use them as conversation context."`

### 14.1 Injected Dependencies

```python
WindowsScreenshotServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
    vision_capable: bool,
)
```

`vision_capable` is set at startup based on whether the active LLM provider
and model support multimodal (image) input. If False, screenshots can still
be captured and saved but cannot be used as direct conversation context.

### 14.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `take_screenshot` | 2 | Capture the full screen and use it as context |
| `take_window_screenshot` | 2 | Capture a specific window by title and use it as context |
| `save_screenshot` | 2 | Capture the screen and save it to a file path |

### 14.3 Implementation

**Capture:** Uses `PIL.ImageGrab.grab()` (from `Pillow`) for full screen
capture. For specific windows, the window is first brought to the foreground
using `pygetwindow`, its position and size are read, and `PIL.ImageGrab.grab(bbox=...)` captures only that region.

**Headless restriction:** Screenshot tools are restricted in headless mode
(see Section 16) — only `save_screenshot` works headlessly. `take_screenshot`
and `take_window_screenshot` (which inject the image into the conversation)
require GUI mode.

**Vision model injection:** When the active model supports multimodal input
(Claude, GPT-4o, Gemini), the captured screenshot is encoded as base64 and
injected directly into the next message to the model as an image block — the
same mechanism used by the `/image` slash command. The AI can then describe,
analyze, or reason about the screen content in its response.

When the active model does not support images, the server uses OCR
(`pytesseract` if installed, or a simpler heuristic text extraction) to extract
text from the screenshot and injects it as a text block instead. OCR
availability is indicated in the tool result.

**Resolution management:** Full-screen captures on high-DPI displays are
automatically scaled to 1920×1080 maximum before encoding if the original
resolution exceeds this — keeping the image size manageable for the model's
vision input while retaining sufficient detail for most use cases.

**Output on success:**

```
Screenshot captured: 1920×1080 px (2.1 MB → 312 KB JPEG)
Mode: injected as conversation context
Model: vision capable ✓
```

---

## 15. WindowsNotificationServer

**File:** `builtin/windows_notification.py`
**Name:** `"windows-notification"`
**Description:** `"Send Windows desktop toast notifications on the user's behalf."`

### 15.1 Injected Dependencies

```python
WindowsNotificationServer(
    safety: WindowsSafetyChecker,
    audit: WindowsAuditLog,
)
```

### 15.2 Tools Exposed

| Tool Name | Tier | Description |
|---|---|---|
| `send_notification` | 2 | Send an immediate Windows toast notification |
| `send_scheduled_notification` | 2 | Send a notification after a delay (e.g., "remind me in 10 minutes") |
| `list_scheduled_notifications` | 1 | List all pending scheduled notifications |
| `cancel_scheduled_notification` | 2 | Cancel a pending scheduled notification by ID |

### 15.3 `send_notification` — Arguments & Behavior

**Argument schema:** `title: str`, `message: str`, `icon: str | None = None`

`title` is the bold notification heading. `message` is the body text.
`icon` is optional — if provided it should be a path to a `.ico` or `.png`
file within the allowed paths list.

Uses `winotify` (preferred, modern Windows 10/11 toast API) or `win10toast`
as fallback. Both are optional dependencies included in `pip install anythink[windows]`.

The notification appears in the Windows notification center and the system
tray popup, exactly as any other Windows application notification does.
Notifications sent by Anythink are identifiable by the "Anythink" application
name shown in the notification header.

### 15.4 `send_scheduled_notification` — Arguments & Behavior

**Argument schema:** `title: str`, `message: str`, `delay_seconds: int | None = None`, `at_time: str | None = None`

Either `delay_seconds` or `at_time` must be provided.
`at_time` accepts a human-readable time string (`"14:30"`, `"2:30 PM"`,
`"tomorrow 9:00 AM"`). It is parsed relative to the current system time.

Scheduled notifications are managed by a lightweight in-process scheduler
(using `asyncio`). They persist for the duration of the session — if Anythink
is closed before the scheduled time, the notification is not sent. The
`list_scheduled_notifications` tool shows all pending notifications with their
IDs and scheduled times, allowing the user to review or cancel them.

---

## 16. Headless vs GUI Mode

### 16.1 What the Modes Mean

**Headless mode** (default): Anythink is running in a terminal session.
The desktop environment exists but may not be visible or interactive. Operations
that require direct GUI interaction (sending keystrokes to windows, injecting
screenshots into conversation) either use programmatic Windows APIs that work
without a visible GUI, or are restricted to their save-to-file variants.

**GUI mode**: Anythink is running in a terminal session where the user has
confirmed that a full interactive desktop is present and visible. All
screenshot and window-interaction features work at their full capability.

### 16.2 Switching Modes

```
/mcp windows mode gui           Enable GUI mode for this session
/mcp windows mode headless      Switch back to headless mode
/settings → Windows → Mode      Persistent setting across sessions
```

GUI mode can also be set as the persistent default in `/settings` → Windows →
Operating mode so it does not need to be set each session.

### 16.3 Tool Availability by Mode

| Tool | Headless | GUI Mode |
|---|---|---|
| All filesystem, system, settings, clipboard, process, notification tools | ✓ Full | ✓ Full |
| `take_screenshot` (inject into conversation) | ✗ Restricted | ✓ Full |
| `take_window_screenshot` | ✗ Restricted | ✓ Full |
| `save_screenshot` (save to file only) | ✓ File save only | ✓ Full |
| `send_text_to_window` | ✗ Unavailable | ✓ Full |
| `navigate_explorer_to_path` (existing window) | ⚠ Limited (new window fallback) | ✓ Full |
| `select_files_in_explorer` | ⚠ Limited (open folder fallback) | ✓ Full |

Tools marked `✗ Unavailable` in headless mode return an informative error:
`"This tool requires GUI mode. Run /mcp windows mode gui to enable."` rather
than failing silently.

---

## 17. Python Dependencies

All new Windows capabilities are optional dependencies installable as:

```
pip install anythink[windows]
```

| Package | Version | Purpose |
|---|---|---|
| `pywin32` | ≥306 | Win32 API: clipboard, file ops, registry, volume, power plans, window control |
| `psutil` | ≥5.9 | Process management, CPU/RAM/disk/battery/network info |
| `pygetwindow` | ≥0.0.9 | Window enumeration, focus, minimize/maximize/restore |
| `pyautogui` | ≥0.9.54 | `typewrite()` for send_text_to_window |
| `Pillow` | ≥10.0 | `ImageGrab.grab()` for screenshots |
| `winotify` | ≥1.1.0 | Windows toast notifications (primary) |
| `win10toast` | ≥0.9 | Notification fallback |

All are imported **inside method bodies only** — never at module level —
maintaining the existing deferred-import pattern that allows the rest of
Anythink to operate on non-Windows platforms or without the `[windows]` extra.
Missing optional packages are caught at the first call to a tool that needs
them, returning a `MCPCallResult(is_error=True)` with an installation hint
rather than raising an unhandled exception.

---

## 18. AppConfig Changes

New fields added to `AppConfig` in `config/schema.py`:

| Field | Type | Default | Description |
|---|---|---|---|
| `windows_enabled` | `bool` | `False` | Master switch for all Windows MCP servers |
| `windows_gui_mode` | `bool` | `False` | GUI mode vs headless mode |
| `windows_allowed_paths` | `list[str]` | `[Documents, Desktop, Downloads]` | Paths the AI is permitted to operate within |
| `windows_blocked_paths` | `list[str]` | See Section 4.3 | Paths always blocked regardless of allowed list |
| `windows_blocked_apps` | `list[str]` | `["regedit.exe", "cmd.exe", "powershell.exe", "mmc.exe"]` | Applications that cannot be launched or killed by the AI |
| `windows_audit_log_enabled` | `bool` | `True` | Enable/disable audit logging |
| `windows_audit_log_path` | `str` | XDG state dir | Override path for audit log file |
| `windows_screenshot_max_px` | `int` | `1920` | Maximum screenshot width in pixels |
| `windows_notification_app_name` | `str` | `"Anythink"` | App name shown in Windows toast notifications |
| `windows_apps_cache_ttl_minutes` | `int` | `60` | How long the installed apps list is cached |

---

## 19. The `/mcp windows` Command Namespace

All Windows-specific management commands live under `/mcp windows`:

### 19.1 Status & Configuration

```
/mcp windows                    Show all Windows server statuses
/mcp windows status             Same as above — detailed server health
/mcp windows mode gui           Enable GUI mode
/mcp windows mode headless      Enable headless mode
```

### 19.2 Path Management

```
/mcp windows paths list         Show allowed and blocked path lists
/mcp windows paths allow <path> Add a path to the allowed list
/mcp windows paths remove <path>Remove a path from the allowed list
/mcp windows paths block <path> Add a path to the blocked list
/mcp windows paths unblock <path> Remove a custom blocked path
                                (default blocked paths cannot be unblocked)
```

### 19.3 App Management

```
/mcp windows apps               List all installed applications
/mcp windows apps refresh       Rebuild the installed apps cache
/mcp windows apps block <name>  Add an app to the blocked-apps list
/mcp windows apps unblock <name>Remove from blocked-apps list
```

### 19.4 Audit Log

```
/mcp windows audit              Show last 20 audit entries
/mcp windows audit --n <count>  Show last N audit entries
/mcp windows audit --tool <name>Filter by tool name
/mcp windows audit --date today Show only today's entries
/mcp windows audit --export     Export full log to text file
/mcp windows audit clear        Clear the audit log (requires confirmation)
```

### 19.5 Quick Actions

```
/mcp windows screenshot         Take and inject a screenshot immediately
/mcp windows clip read          Read clipboard content
/mcp windows clip write <text>  Write text to clipboard
/mcp windows notify <message>   Send an immediate desktop notification
```

---

## 20. Registration in AppContext

In `app/context.py`, the ten new servers are registered conditionally —
only when `config.windows_enabled` is `True` and `sys.platform == "win32"`.
Non-Windows platforms or users who have not enabled Windows integration skip
registration entirely:

```
MCPManager(
    builtin_servers=[
        # Existing servers — always registered
        FilesystemServer(data_dir),
        SessionsServer(session_manager),
        RAGServer(rag_engine, embedding_model),
        SearchServer(search_registry),

        # New Windows servers — registered only when enabled on Windows
        *windows_servers,   ← conditional list built below
    ]
)
```

The `windows_servers` list is built in a separate function in `app/context.py`
that:

1. Checks `sys.platform == "win32"` and `config.windows_enabled`
2. Instantiates the three shared cross-cutting components:
   `WindowsPathGuard(config)`, `WindowsSafetyChecker()`,
   `WindowsAuditLog(config.windows_audit_log_path)`
3. Constructs all ten server instances with their required dependencies
4. Returns the list to be spread into `MCPManager(builtin_servers=...)`

If `windows_enabled` is `False` or the platform is not Windows, the function
returns an empty list — no Windows servers are registered, no Windows
dependencies are imported, and the rest of Anythink is completely unaffected.

---

## 21. Architecture Changes Summary

### 21.1 New Components

| Component | File | Purpose |
|---|---|---|
| `WindowsPathGuard` | `windows/paths.py` | Validates all paths against allowed/blocked lists |
| `WindowsSafetyChecker` | `windows/safety.py` | Classifies tools into Tiers 1–4, enforces confirmation |
| `WindowsAuditLog` | `windows/audit.py` | Writes every tool call to the persistent JSONL audit log |
| `WindowsFilesystemServer` | `builtin/windows_filesystem.py` | Full file CRUD |
| `WindowsExplorerServer` | `builtin/windows_explorer.py` | File Explorer control |
| `WindowsAppsServer` | `builtin/windows_apps.py` | Application discovery and launching |
| `WindowsWindowServer` | `builtin/windows_window.py` | Window enumeration and control |
| `WindowsProcessServer` | `builtin/windows_process.py` | Process management |
| `WindowsSystemServer` | `builtin/windows_system.py` | System information |
| `WindowsSettingsServer` | `builtin/windows_settings.py` | System settings |
| `WindowsClipboardServer` | `builtin/windows_clipboard.py` | Clipboard read/write |
| `WindowsScreenshotServer` | `builtin/windows_screenshot.py` | Screen capture |
| `WindowsNotificationServer` | `builtin/windows_notification.py` | Toast notifications |

### 21.2 Modified Components

| Component | What Changes |
|---|---|
| `app/context.py` | Conditional Windows server registration block added |
| `config/schema.py` | All new `AppConfig` fields from Section 18 |
| `commands/handlers.py` | `/mcp windows` sub-command namespace added |

### 21.3 Unchanged Components

| Component | Status |
|---|---|
| `mcp/models.py` | Unchanged |
| `mcp/manager.py` | Unchanged |
| `mcp/client.py` | Unchanged |
| `mcp/server.py` | Unchanged |
| `mcp/builtin/base.py` | Unchanged |
| `mcp/builtin/filesystem.py` | Unchanged |
| `mcp/builtin/rag.py` | Unchanged |
| `mcp/builtin/search.py` | Unchanged |
| `mcp/builtin/sessions.py` | Unchanged |

### 21.4 Complete Tool Roster — All 10 Windows Servers

| Server | Tools | Total |
|---|---|---|
| WindowsFilesystemServer | list_dir, read_file, get_file_metadata, search_files_by_name, search_files_by_content, write_file, create_file, create_folder, copy_file, move_file, rename_file, delete_file, delete_folder | 13 |
| WindowsExplorerServer | open_folder_in_explorer, navigate_explorer_to_path, open_file_with_default_app, select_files_in_explorer | 4 |
| WindowsAppsServer | list_installed_apps, launch_app | 2 |
| WindowsWindowServer | list_open_windows, bring_to_foreground, minimize_window, maximize_window, restore_window, close_window, send_text_to_window | 7 |
| WindowsProcessServer | list_processes, get_process_info, start_process, kill_process | 4 |
| WindowsSystemServer | get_cpu_info, get_ram_info, get_disk_info, get_battery_info, get_network_info, get_windows_version, get_hardware_info, get_installed_apps | 8 |
| WindowsSettingsServer | get_volume, set_volume, mute_audio, get_brightness, set_brightness, get_power_plan, list_power_plans, set_power_plan, get_timezone, set_timezone, get_display_info | 11 |
| WindowsClipboardServer | read_clipboard, write_clipboard, clear_clipboard | 3 |
| WindowsScreenshotServer | take_screenshot, take_window_screenshot, save_screenshot | 3 |
| WindowsNotificationServer | send_notification, send_scheduled_notification, list_scheduled_notifications, cancel_scheduled_notification | 4 |
| **Total** | | **59 tools** |

---

*Anythink — Think anything. Ask anything.*

*Version described: Windows OS MCP Integration Build*
*Document last updated: June 2025*
