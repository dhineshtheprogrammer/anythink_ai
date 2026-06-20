# Anythink

> Think anything. Ask anything.

[![CI](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/anythink)](https://pypi.org/project/anythink/)
[![Python](https://img.shields.io/pypi/pyversions/anythink)](https://pypi.org/project/anythink/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Anythink 2.0** is a universal AI terminal workstation. A Textual-powered TUI that brings RAG, agentic tools, MCP, voice, notifications, and a 4-panel dashboard to your terminal — alongside the original multi-provider LLM chat experience from v1.

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
```

---

## CLI Reference

```bash
anythink                    # Simple Chat Mode
anythink --dashboard / -D   # 4-panel Dashboard Mode
anythink --version / -V     # Show version

anythink keys list|add|show|update|delete|test <provider>
anythink model list|add|remove
anythink plugins list|info|install|remove
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
| Sessions | `~/.local/share/anythink/sessions/` |
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
