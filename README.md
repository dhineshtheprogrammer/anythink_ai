# Anythink

> Think anything. Ask anything.

[![CI](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml/badge.svg)](https://github.com/dhineshtheprogrammer/anythink_ai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/anythink)](https://pypi.org/project/anythink/)
[![Python](https://img.shields.io/pypi/pyversions/anythink)](https://pypi.org/project/anythink/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Anythink** is a universal, AI-powered CLI chatbot with a beautiful terminal interface, multi-provider LLM support, and an extensible plugin architecture. Built in Python 3.11+. Installable from PyPI.

---

## Features

- **Multi-provider** — Groq, Google Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio, llama.cpp
- **Rich terminal UI** — real-time token streaming, markdown rendering, 4 color themes
- **Model aliases** — give your models friendly personal names (`google2`, `groqfast`)
- **Session management** — auto-save conversations, resume sessions, search history
- **File & image input** — attach source files and images to any message
- **Agentic web search** — DuckDuckGo (free) or SerpAPI, auto-injects results as context
- **Plugin architecture** — extend providers, search backends, and slash commands via PyPI packages
- **Full CLI** — manage keys, models, and plugins without entering a chat session

---

## Installation

```bash
pip install anythink
```

Install with a specific provider's SDK:

```bash
pip install anythink[groq]       # Groq
pip install anythink[gemini]     # Google Gemini
pip install anythink[openai]     # OpenAI
pip install anythink[anthropic]  # Anthropic
pip install anythink[mistral]    # Mistral
pip install anythink[cohere]     # Cohere
pip install anythink[search]     # DuckDuckGo web search
pip install anythink[all]        # Everything
```

---

## Quick Start

```bash
# First run — set up a provider and model alias
anythink keys add groq
anythink model add          # interactive: alias=mygroq, model=llama3-8b-8192, ctx=8192
anythink                    # start chatting

# Or with a different provider
anythink keys add openai
anythink model add          # alias=gpt4o, provider=openai, model=gpt-4o, ctx=128000
anythink
```

---

## CLI Reference

### Chat

```bash
anythink                    # Start interactive chat session
anythink --version          # Show version
```

### Key Management

```bash
anythink keys list                  # List configured providers
anythink keys add <provider>        # Add API key (masked prompt)
anythink keys show <provider>       # Show masked key
anythink keys update <provider>     # Replace existing key
anythink keys delete <provider>     # Delete key (--yes to skip confirm)
anythink keys test <provider>       # Validate key with a live API call
```

### Model Aliases

```bash
anythink model list                 # Show all aliases in a table
anythink model add                  # Interactive alias creation
anythink model remove <alias>       # Remove alias (--yes to skip confirm)
```

### Plugins

```bash
anythink plugins list               # List installed plugins
anythink plugins info <pkg>         # Show plugin details
anythink plugins install <pkg>      # pip install + register
anythink plugins remove <pkg>       # pip uninstall
```

---

## Slash Commands

Available inside any chat session:

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/clear` | Clear conversation history |
| `/history` | Show recent messages |
| `/tokens` | Show context window usage |
| `/model` | Show active provider and model |
| `/persona <name>` | Activate a saved persona |
| `/persona clear` | Remove active persona |
| `/session save [name]` | Save current session |
| `/session load <id>` | Load a saved session |
| `/session list` | List saved sessions |
| `/session delete <id>` | Delete a session |
| `/session rename <id> <name>` | Rename a session |
| `/file <path>` | Attach a text file to the next message |
| `/image <path>` | Attach an image (multimodal models) |
| `/files` | List pending attachments |
| `/search on` | Enable auto web search for all messages |
| `/search off` | Disable auto web search |
| `/search <query>` | Run a one-off web search |
| `/plugins` | List installed plugins |
| `/plugins info <name>` | Show plugin details |
| `/plugins install <pkg>` | Install a plugin |
| `/plugins remove <pkg>` | Remove a plugin |
| `/exit` or `/quit` | End the session |

---

## Configuration

Anythink stores all data under the XDG Base Directory hierarchy:

| File / Directory | Default Location |
|---|---|
| Main config | `~/.config/anythink/config.yaml` |
| Model aliases | `~/.config/anythink/models.yaml` |
| Personas | `~/.config/anythink/personas.yaml` |
| Sessions | `~/.local/share/anythink/sessions/` |
| Logs | `~/.local/state/anythink/logs/` |

Key `config.yaml` options:

```yaml
default_model_alias: mygroq
active_theme: midnight          # midnight | aurora | ember | arctic
web_search_enabled: false
search_provider: duckduckgo     # duckduckgo | serpapi
session_autosave: true
```

---

## Adding Plugins

Plugins are standard PyPI packages that register entry points in the `anythink.*` namespace:

```toml
# pyproject.toml of your plugin
[project.entry-points."anythink.providers"]
myprovider = "anythink_myprovider:MyProvider"

[project.entry-points."anythink.slash_commands"]
mycommands = "anythink_myprovider.commands:register_commands"
```

Anythink discovers them automatically on next startup. No core code changes needed.

---

## Development

```bash
git clone https://github.com/dhineshtheprogrammer/anythink_ai
cd anythink_ai
pip install -e ".[dev]"

# Lint
ruff check src/
black --check src/ tests/

# Type check
mypy src/anythink

# Tests (80% coverage enforced)
PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring pytest tests/ -v

# Security scan
bandit -r src/anythink -c pyproject.toml

# Build
python -m build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## License

MIT — see [LICENSE](LICENSE) for details.
