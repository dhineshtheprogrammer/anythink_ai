# Anythink

> Think anything. Ask anything.

[![CI](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/PyPI-3.0.0-blue?logo=pypi&logoColor=white)](https://pypi.org/project/anythink/3.0.0/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python&logoColor=white)](https://pypi.org/project/anythink/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Anythink 3.0** is a universal AI terminal workstation. A Textual-powered TUI that brings RAG, agentic tools, MCP, voice, notifications, a 4-panel dashboard, and now a full automation and cost-awareness layer to your terminal.

---

## Features

### Core
- **Multi-provider** — Groq, Google Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio
- **Textual TUI** — chat bubbles, streaming markdown, 4 color themes, persistent HUD
- **Model aliases** — give models friendly names (`groq-fast`, `claude`)
- **Session management** — auto-save, naming, undo, bookmarks, conversation branches
- **File & image input** — attach source files and images to any message

### V2 Capabilities
- **RAG** — index local folders, retrieve relevant chunks, transparent `📚 Retrieved from N sources` footer
- **Code execution** (`/exec python ...`) — runs code in your environment; ask/auto approval; result fed to AI
- **Agentic browsing** (`/browse`) — snippet search + full-page httpx fetch; ask/auto modes
- **MCP** — built-in servers (filesystem, sessions, RAG, search) + connect external MCP servers
- **Dashboard mode** (`--dashboard` or `Ctrl+D`) — 4 panels: session list, stats, file browser, RAG browser, tool output log
- **Voice input** (`/voice`) — mic capture → local Whisper transcription → editable text in input
- **Desktop notifications** — RAG build done, slow response, exec, browse, provider failure

### V3 Capabilities
- **Per-model generation parameters** — tune temperature, max tokens, top-p, frequency/presence penalty per alias (`/params`)
- **Multi-model comparison** — send one prompt to multiple aliases simultaneously; pick which response to continue with (`/compare`)
- **Spend tracking** — estimated USD cost per response, session, day, month; HUD cost indicator; optional soft budget limit (`/cost`)
- **Prompt templates** — save reusable prompts with `{{variable}}` placeholders; instantiate with inline args (`/template`, `/use`)
- **Session export** — export conversations to Markdown, JSON, or PDF (`/export`)
- **Scheduled prompts** — set recurring prompts on a cron schedule; output to file or notification (`/schedule`, `anythink scheduler`)
- **Batch processing** — run a file full of prompts non-interactively; parallel execution; Markdown or JSON output (`anythink run`)
- **Self-update** — check and install updates directly from PyPI (`/update`)
- **Diagnostics** — comprehensive health check: Python version, deps, API keys, local servers, config, disk (`/doctor`, `anythink doctor`)
- **Config backup & restore** — export your full setup as a portable JSON bundle; import on any machine (`/config export|import`)

---

## Installation

```bash
# Base install (all providers via lazy imports, no heavy extras)
pip install anythink
```

### Optional extras

| Extra | Installs | Use case |
|---|---|---|
| `pip install anythink[groq]` | groq SDK | Groq cloud inference |
| `pip install anythink[openai]` | openai SDK | OpenAI / Azure |
| `pip install anythink[anthropic]` | anthropic SDK | Claude models |
| `pip install anythink[gemini]` | google-generativeai | Gemini Pro / Flash |
| `pip install anythink[mistral]` | mistralai SDK | Mistral models |
| `pip install anythink[cohere]` | cohere SDK | Cohere Command |
| `pip install anythink[search]` | duckduckgo-search | Free web search |
| `pip install anythink[rag]` | sentence-transformers | Local RAG embeddings |
| `pip install anythink[voice]` | openai-whisper + sounddevice | Voice input |
| `pip install anythink[browser]` | playwright | Headless web browsing |
| `pip install anythink[mcp]` | mcp SDK | External MCP server connections |
| `pip install anythink[pdf]` | fpdf2 | PDF session export |
| `pip install anythink[scheduler]` | croniter | Cron-based scheduled prompts |
| `pip install anythink[all]` | Everything above | Full workstation |

---

## Quick Start

```bash
# Set up a provider and model alias
anythink keys add groq
anythink model add          # alias=groq-fast, provider=groq, model=llama3-8b-8192

# Start chatting (Simple Chat Mode)
anythink

# Or launch the 4-panel Dashboard
anythink --dashboard

# Run a batch of prompts non-interactively
anythink run --file prompts.txt --output results.md

# Check your installation health
anythink doctor
```

---

## CLI Reference

```bash
# Chat
anythink                    # Simple Chat Mode
anythink --dashboard / -D   # 4-panel Dashboard Mode
anythink --version / -V     # Show version

# Key & model management
anythink keys list|add|show|update|delete|test <provider>
anythink model list|add|remove

# Plugins
anythink plugins list|info|install|remove

# V3: Batch processing (non-interactive)
anythink run --file prompts.txt --output results.md [--parallel N] [--alias A] [--format md|json]

# V3: Diagnostics
anythink doctor

# V3: Scheduled prompt automation
anythink scheduler start [--poll 60]   # Foreground loop, checks every N seconds
anythink scheduler run <name>          # Run a schedule immediately
anythink scheduler list                # Show all schedules and their status
```

---

## Slash Commands

### Chat & History
| Command | Description |
|---|---|
| `/help` | List all commands |
| `/clear` | Clear conversation history |
| `/history` | Show recent messages |
| `/tokens` | Context window usage |
| `/model` | Active provider and model |
| `/persona <name>` | Activate a saved persona |
| `/persona clear` | Remove active persona |
| `/exit` / `/quit` | End the session |

### Sessions & Branches
| Command | Description |
|---|---|
| `/rename <name>` | Rename current session |
| `/session save|load|list|delete|rename` | Session management |
| `/undo` | Remove last exchange |
| `/bookmark [turn]` | Bookmark an AI response |
| `/bookmarks` | List bookmarks |
| `/bookmark export [path]` | Export bookmarks to file |
| `/branch` | Create a conversation branch |
| `/branch list` | List all branches |
| `/branch switch <name>` | Switch to branch |

### Files & Search
| Command | Description |
|---|---|
| `/file <path>` | Attach a text file |
| `/image <path>` | Attach an image |
| `/files` | List pending attachments |
| `/search on|off|<query>` | Web search control |

### RAG
| Command | Description |
|---|---|
| `/rag new <name>` | Create a new RAG index |
| `/rag use <name>` | Activate an index |
| `/rag off` | Deactivate RAG |
| `/rag list` | List indexes |
| `/rag rebuild [name]` | Rebuild an index |
| `/rag info [name]` | Show index details |
| `/rag status` | Show active index |

### Tools
| Command | Description |
|---|---|
| `/exec <lang> <code>` | Run code in your environment |
| `/exec mode ask\|auto` | Change exec approval mode |
| `/browse <url\|query>` | Fetch web page or search |
| `/browse mode ask\|auto\|http\|headless` | Change browse mode |

### MCP
| Command | Description |
|---|---|
| `/mcp list` | List registered servers |
| `/mcp tools` | List available tools |
| `/mcp call <tool> [k=v ...]` | Call a tool |
| `/mcp connect <name> stdio <cmd>` | Connect to external server |
| `/mcp disconnect <name>` | Disconnect |
| `/mcp server start\|stop\|status` | Run Anythink as MCP server |

### Voice & Notifications
| Command | Description |
|---|---|
| `/voice` | Start recording (Enter to stop) |
| `/voice model tiny\|base\|small\|medium\|large\|turbo` | Set Whisper model |
| `/voice language <code>` | Pin transcription language |
| `/notify on\|off\|status` | Notification control |
| `/notify type <name> on\|off` | Per-type toggle |

### V3 — Model Parameters & Spend
| Command | Description |
|---|---|
| `/params` | Show generation params for the active alias |
| `/params temperature=0.3 max_tokens=2048 top_p=0.9` | Set params (key=value pairs) |
| `/params reset` | Reset to provider defaults |
| `/cost` | Session spend estimate |
| `/cost today` | Today's spend across all sessions |
| `/cost month` | This month's spend |
| `/cost by-model` | Lifetime spend broken down per model |
| `/cost by-provider` | Lifetime spend broken down per provider |

### V3 — Templates
| Command | Description |
|---|---|
| `/template save <name> <body>` | Save a prompt template (supports `{{variable}}`) |
| `/template list` | List all saved templates |
| `/template show <name>` | Preview a template |
| `/template delete <name>` | Remove a template |
| `/use <name> [key=value ...]` | Render a template and send as next message |

### V3 — Export & Compare
| Command | Description |
|---|---|
| `/export` | Export session as Markdown (default) |
| `/export json [path]` | Export as JSON |
| `/export pdf [path]` | Export as PDF (`pip install anythink[pdf]`) |
| `/export markdown --range 1-10` | Export a turn range |
| `/compare <alias1> <alias2> [...]` | Compare up to 4 models on the next prompt |

### V3 — Scheduling
| Command | Description |
|---|---|
| `/schedule list` | List all scheduled prompts |
| `/schedule add <name> "<cron>" <prompt>` | Create a scheduled prompt |
| `/schedule enable <name>` | Enable a paused schedule |
| `/schedule disable <name>` | Pause a schedule |
| `/schedule remove <name>` | Delete a schedule |
| `/schedule run <name>` | Run a schedule immediately |

### V3 — Maintenance
| Command | Description |
|---|---|
| `/doctor` | Full installation health check |
| `/update check` | Check for a newer version on PyPI |
| `/update` | Upgrade Anythink to the latest version |
| `/config export [path]` | Export config as a portable JSON bundle |
| `/config import <path>` | Restore config from a bundle |

### Dashboard Shortcuts
| Key | Action |
|---|---|
| `Ctrl+D` | Toggle Simple / Dashboard mode |
| `Ctrl+L` | Toggle Sessions panel |
| `Ctrl+R` | Toggle Stats panel |
| `Tab` | Cycle bottom tabs |
| `Escape` | Return focus to input |

---

## Configuration

All data stored under the XDG Base Directory hierarchy:

| Path | Default |
|---|---|
| Config | `~/.config/anythink/config.yaml` |
| Models | `~/.config/anythink/models.yaml` |
| Templates | `~/.config/anythink/templates.yaml` |
| Schedules | `~/.config/anythink/schedules.yaml` |
| Sessions | `~/.local/share/anythink/sessions/` |
| Exports | `~/.local/share/anythink/exports/` |
| Spend log | `~/.local/share/anythink/spend.yaml` |
| RAG metadata | `~/.local/share/anythink/rag/` |
| RAG vectors | `~/.cache/anythink/rag/` |

Key `config.yaml` options:

```yaml
active_theme: midnight          # midnight | aurora | ember | arctic
default_model_alias: groq-fast
session_autosave: true
search_provider: duckduckgo
embedding_backend: local        # local | api
exec_mode: ask                  # ask | auto
browse_mode: http               # http | headless
browse_autonomy: ask            # ask | auto
voice_model: base               # tiny|base|small|medium|large|turbo

# V3 spend tracking
spend_tracking: true
spend_budget_period: monthly    # monthly | daily
spend_budget_soft_limit: null   # e.g. 10.0 for a $10 soft limit
```

---

## Development

```bash
git clone https://github.com/dhineshtheprogrammer/anythink_ai
cd anythink_ai
pip install -e ".[all,dev]"

ruff check src/
black --check src/ tests/
mypy src/anythink
bandit -r src/anythink -c pyproject.toml
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [CHANGELOG.md](CHANGELOG.md) for release history.

---

## License

MIT — see [LICENSE](LICENSE) for details.
