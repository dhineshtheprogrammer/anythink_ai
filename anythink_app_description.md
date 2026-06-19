# Anythink — Detailed Application Description

> A universal, AI-powered CLI chatbot with a beautiful terminal interface, multi-provider LLM support, and an extensible plugin architecture. Built in Python. Distributed as an open-source PyPI package.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Visual Identity & Look](#2-visual-identity--look)
3. [Terminal UI & Interaction Design](#3-terminal-ui--interaction-design)
4. [LLM Provider Architecture](#4-llm-provider-architecture)
5. [Model Identity & Alias System](#5-model-identity--alias-system)
6. [API Key & Credential Management](#6-api-key--credential-management)
7. [Core Chat Functionality](#7-core-chat-functionality)
8. [Session & History Management](#8-session--history-management)
9. [Context Window Awareness](#9-context-window-awareness)
10. [Slash Command System](#10-slash-command-system)
11. [File Input & Multimodal Support](#11-file-input--multimodal-support)
12. [Agentic Web Search](#12-agentic-web-search)
13. [Plugin Architecture](#13-plugin-architecture)
14. [Configuration & Storage](#14-configuration--storage)
15. [First-Run Setup Wizard](#15-first-run-setup-wizard)
16. [PyPI Distribution & Open Source](#16-pypi-distribution--open-source)
17. [Testing & CI Pipeline](#17-testing--ci-pipeline)
18. [Future Roadmap](#18-future-roadmap)

---

## 1. Overview

**Anythink** is a terminal-native AI assistant CLI application written in Python. It functions as a universal LLM chatbot interface — meaning it is designed from the ground up to work with any LLM provider: Groq, Google Gemini, local models via Ollama, LM Studio, llama.cpp, and any future provider added via the plugin system.

The application draws strong inspiration from Claude Code's terminal UX — rich markdown rendering, real-time token streaming, multi-line input, and slash commands — while introducing its own identity through branding, a user-controlled model alias system, and a first-class plugin architecture.

Anythink is fully open source, installable via `pip install anythink`, and targets Python 3.11+.

---

## 2. Visual Identity & Look

### 2.1 App Name

The application is named **Anythink**. The CLI command is `anythink`. The PyPI package is `anythink`.

### 2.2 ASCII Logo

On every startup, Anythink displays a prominent ASCII art logo in the terminal. The logo spells out "ANYTHINK" in a bold stylized font. Below the logo, the version number, current model alias, and provider name are shown.

Example startup banner area (conceptual layout):

```
 █████╗ ███╗   ██╗██╗   ██╗████████╗██╗  ██╗██╗███╗   ██╗██╗  ██╗
██╔══██╗████╗  ██║╚██╗ ██╔╝╚══██╔══╝██║  ██║██║████╗  ██║██║ ██╔╝
███████║██╔██╗ ██║ ╚████╔╝    ██║   ███████║██║██╔██╗ ██║█████╔╝
██╔══██║██║╚██╗██║  ╚██╔╝     ██║   ██╔══██║██║██║╚██╗██║██╔═██╗
██║  ██║██║ ╚████║   ██║      ██║   ██║  ██║██║██║ ╚████║██║  ██╗
╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝

 Think anything. Ask anything.
 v0.1.0  |  Model: google2 (gemini-2.0-flash)  |  Provider: Gemini
```

### 2.3 Color Themes

Anythink ships with **4 built-in color themes**, selectable by the user at first-run or anytime via a slash command or config. Each theme has a distinct personality. All themes are designed to be readable, non-garish, and visually cohesive in both dark and light terminal backgrounds.

| Theme Name | Personality | Primary | Accent | Highlight | Muted |
|---|---|---|---|---|---|
| **Midnight** *(default)* | Dark, deep blue-violet | Deep Indigo | Electric Cyan | Bright White | Cool Gray |
| **Aurora** | Green terminal nostalgia | Forest Green | Amber Yellow | Lime Green | Slate Gray |
| **Ember** | Warm, orange-red energy | Deep Rust | Soft Gold | Cream White | Charcoal |
| **Arctic** | Clean, minimal icy blue | Steel Blue | Teal | White | Light Gray |

Each theme applies consistently to:
- The ASCII startup banner
- User input prompt
- AI response text
- Streaming output color
- Code block borders and syntax highlight base tone
- Status bar and context window indicator
- Slash command output
- Warning and error messages

---

## 3. Terminal UI & Interaction Design

### 3.1 Multi-Line Input Editor

The user input area functions exactly like Claude Code's multi-line input. The user types on a styled prompt line. To go to a new line within the same message, they press `Shift+Enter` or use a `\` continuation (backslash at end of line). To submit the message, they press `Enter` on a non-continued line. Arrow keys navigate history. The prompt indicator visually distinguishes between a new message start and a continuation line.

Input prompt display example:

```
╭─ You ─────────────────────────────────────
│ Explain how transformers work in detail.
│ Also give me a Python example.
╰──────────────────────────────────────────
```

### 3.2 Real-Time Token Streaming

AI responses are streamed token-by-token from the LLM provider in real time — just like Claude Code's streaming experience. The text appears progressively as it is generated. A subtle animated spinner is shown while waiting for the first token. The streaming cursor blinks at the end of the current output line.

Response display example:

```
╭─ Anythink · google2 ──────────────────────
│
│  A **transformer** is a deep learning model...
│  ▋
╰──────────────────────────────────────────
```

Once the response is complete, the full response is re-rendered with full Markdown formatting (see below).

### 3.3 Rich Markdown Rendering

All AI responses are rendered using full terminal Markdown support. Elements rendered include:

- **Bold** and *italic* text
- `Inline code` with distinct background tinting
- Multi-language **code blocks** with full syntax highlighting (Python, JS, Bash, SQL, JSON, YAML, etc.), rendered with a visible language label and border
- **Tables** — properly aligned with column separators, header row styling
- Ordered and unordered **lists**
- **Blockquotes** with a left-border gutter character
- **Headings** (H1–H4) in progressively smaller but visually distinct styles
- **Horizontal rules** as separator lines
- **Links** displayed as `[text](url)` with the URL in muted accent color

Code block example rendering:

```
 ┌─ python ──────────────────────────────────────┐
 │  import torch                                  │
 │  from transformers import AutoModel            │
 │                                                │
 │  model = AutoModel.from_pretrained("bert")     │
 └────────────────────────────────────────────────┘
```

---

## 4. LLM Provider Architecture

### 4.1 Supported Providers

Anythink is built around a **provider abstraction layer** — every LLM provider implements the same internal interface. This means the rest of the application (chat loop, streaming, file input, web search) is completely provider-agnostic.

At launch, Anythink supports the following providers natively:

| Provider Category | Supported Runtimes / APIs |
|---|---|
| **Cloud: Groq** | Groq API (llama3, mixtral, gemma, etc.) |
| **Cloud: Google** | Gemini API (gemini-2.0-flash, gemini-pro, etc.) |
| **Cloud: OpenAI** | OpenAI API (gpt-4o, gpt-4-turbo, etc.) |
| **Cloud: Anthropic** | Claude API (claude-3-5-sonnet, etc.) |
| **Cloud: Mistral** | Mistral API |
| **Cloud: Cohere** | Cohere API |
| **Local: Ollama** | Ollama (any pulled model) |
| **Local: LM Studio** | LM Studio local server (OpenAI-compatible API) |
| **Local: llama.cpp** | llama.cpp server (http API) |
| **Plugin Providers** | Any future provider via plugin (see Section 13) |

### 4.2 Provider Selection on First Run

When the user runs `anythink` for the very first time, the setup wizard asks them to choose a provider (see Section 15 for full wizard details). The selected provider and its configuration become the **default provider**.

### 4.3 Automatic Provider Fallback

If the current active provider fails (API error, key invalid, local server unreachable, rate limit, timeout), Anythink:

1. Detects the failure and displays a clear, friendly error message describing why the provider failed.
2. Immediately asks the user interactively: *"Provider [X] is not available. Which provider would you like to switch to?"*
3. Displays the user's list of configured model aliases to choose from.
4. Switches to the selected provider/model for the remainder of the session.
5. Optionally asks if the user wants to make the new selection the new default.

This fallback is non-destructive — the conversation history up to the point of failure is preserved and handed to the new provider.

### 4.4 Mid-Session Model Switching

During any active session, the user can switch models at any time using the `/model` slash command. When switching, Anythink asks whether to:

- **Continue the current conversation** with the new model (sends history to new model)
- **Start a fresh session** with the new model

---

## 5. Model Identity & Alias System

This is one of Anythink's most distinctive features. Users do not need to remember raw provider model strings. Instead, they give their models **personal names (aliases)** that Anythink remembers permanently.

### 5.1 How Aliasing Works

The first time a user configures a model, Anythink asks two questions:

1. *"What do you want to call this model? (your personal name)"*
   → Example: `google2`

2. *"What is the actual model identifier for this?"*
   → Example: `gemini-2.0-flash`

Anythink stores this alias-to-model mapping in the user's config. From that point forward, `google2` is a valid model reference everywhere in the app — in `/model` commands, at startup selection, in session history, and in status displays.

### 5.2 Alias Registry

The alias registry is a user-owned lookup table. Each entry stores:

- **Alias name** (user-chosen, e.g. `google2`)
- **Provider** (e.g. `gemini`)
- **Actual model string** (e.g. `gemini-2.0-flash`)
- **Date added**
- **Context window size** (fetched at time of configuration, or entered manually for local models)

### 5.3 Model Selection Menu

Any time Anythink needs the user to choose a model (startup, `/model`, fallback), it displays a formatted selection menu showing only the user's aliases — not raw model strings. The menu also shows each model's provider and context window size.

Example model selection menu:

```
 Select a model:

  1.  google2       gemini-2.0-flash         Gemini      1,000,000 tokens
  2.  groqfast      llama3-8b-8192           Groq            8,192 tokens
  3.  local1        llama3.2:3b              Ollama         32,768 tokens
  4.  gpt4o         gpt-4o                   OpenAI        128,000 tokens

  [ Add new model ]
  [ Remove a model ]
```

---

## 6. API Key & Credential Management

### 6.1 Storage — System Keychain

All API keys are stored in the **OS system keychain**, not in plain text files or environment variables. On macOS this is Keychain Access. On Linux this is the Secret Service API (via `libsecret`, compatible with GNOME Keyring and KWallet). On Windows this is the Windows Credential Manager.

This means API keys are encrypted at rest by the operating system, protected by the user's OS login, and never written to disk by Anythink.

### 6.2 Key Management via Terminal

Anythink provides a dedicated `anythink keys` sub-command group for full CRUD management of credentials:

| Command | Action |
|---|---|
| `anythink keys list` | Show all stored provider keys (names only, values masked) |
| `anythink keys add <provider>` | Interactively enter and save an API key for a provider |
| `anythink keys show <provider>` | Display the stored key (masked, with option to reveal) |
| `anythink keys update <provider>` | Replace an existing key with a new one |
| `anythink keys delete <provider>` | Remove a key from the keychain |
| `anythink keys test <provider>` | Validate the stored key by making a lightweight API test call |

All key operations from within a running chat session are also accessible via `/keys` slash commands, without needing to exit and re-enter.

### 6.3 Local Model Credentials

Local models (Ollama, LM Studio, llama.cpp) do not use API keys. Instead, Anythink stores their **host URL and port** in the config file (not keychain). These are simple values like `http://localhost:11434` and are not sensitive.

---

## 7. Core Chat Functionality

### 7.1 Conversational Chat Loop

Anythink runs a persistent chat loop in the terminal. The user types a message, submits it, and sees the streaming AI response. The conversation continues turn-by-turn. The full message history for the session is maintained in memory and, depending on context window limits, trimmed intelligently.

### 7.2 Persona / System Prompt per Session

Each session can be started with a specific **persona** — a custom system prompt that shapes how the AI behaves for that session. The user can:

- Choose a persona from a saved list at session start
- Define a new persona inline at the start of a session
- Use the default (no persona / general assistant)

Personas are stored by name in config (e.g., `python-expert`, `code-reviewer`, `creative-writer`). Personas are not shared across sessions unless explicitly set. They can be managed with `/persona` slash commands.

Example persona definition stored in config:

```
Name: python-expert
System Prompt: You are an expert Python software engineer with 20 years of experience. 
               You always write clean, PEP-8 compliant code and explain your reasoning.
```

### 7.3 Message Roles & Display

The chat UI clearly distinguishes between:

- **User messages** — shown in the user's theme primary color with a "You" label
- **AI responses** — shown in a distinct accent color with the model alias as the label
- **System messages / tool output** — shown in muted color with an icon indicator
- **Error messages** — shown in a red/warning color with a ⚠ prefix

---

## 8. Session & History Management

### 8.1 Automatic Session Saving

Every conversation session is **automatically saved** to disk as a plain text file. The user does not need to manually trigger a save. Sessions are saved in real time — after each exchange — so nothing is lost if the terminal crashes.

### 8.2 Plain Text File Format

Sessions are stored as human-readable plain text files. Each file contains:

- A header block with metadata (session ID, date/time, model alias, provider, persona used)
- Each message in clearly delimited turn blocks (USER / ASSISTANT / SYSTEM)
- Timestamps per turn
- File/image references if any were used in that turn
- Web search references if any were triggered

The plain text format is intentionally simple so users can read, search, copy, or share sessions without any special tooling.

### 8.3 Session File Location

Sessions are stored at: `$XDG_DATA_HOME/anythink/sessions/` (defaults to `~/.local/share/anythink/sessions/` on Linux/macOS).

Each file is named: `YYYY-MM-DD_HHMMSS_<alias>_<short-id>.txt`

Example: `2025-06-18_143022_google2_a1b2.txt`

### 8.4 Session Management Commands

| Slash Command | Action |
|---|---|
| `/history` | List recent sessions with date, model, message count |
| `/history open <id>` | Load and resume a previous session |
| `/history search <query>` | Search across all session files by keyword |
| `/history delete <id>` | Delete a specific session file |
| `/export` | Export current session to a named file location |

---

## 9. Context Window Awareness

Context window awareness is a first-class feature in Anythink, visible at all times.

### 9.1 Context Window Display at Model Selection

When the user selects or switches a model, the context window size is always shown alongside the model name. Example:

```
  google2   gemini-2.0-flash   1,000,000 tokens context
```

### 9.2 Live Context Window Indicator During Session

A persistent **context status line** is shown at the bottom of the terminal (or as a header line, theme-dependent). It shows in real time:

```
 Context:  ████████░░░░░░░░░░░░░░░░  12,400 / 128,000 tokens used  (9.7%)
```

This updates after every exchange. The progress bar fills and changes color as usage increases:
- **Green** (0–60%): Safe zone
- **Yellow** (60–85%): Approaching limit
- **Orange** (85–95%): High usage warning
- **Red** (95%+): Critical — approaching limit

### 9.3 Approaching-Limit Warnings

At 85% context usage, Anythink displays an inline warning after the AI response:

```
 ⚠ Context Warning: You have used 85% of this model's context window.
   Consider /clear to reset the conversation or /model to switch to a larger-context model.
```

At 95%, a more urgent warning is shown, and the user is asked whether to auto-summarize and compress history, or start fresh.

---

## 10. Slash Command System

Anythink implements a comprehensive slash command system inspired by Claude Code. All slash commands begin with `/` and are available at any point during a session.

### 10.1 Built-in Slash Commands

**Session & Navigation**

| Command | Description |
|---|---|
| `/help` | Show all available slash commands with descriptions |
| `/exit` or `/quit` | End the session (prompts to save if unsaved changes) |
| `/clear` | Clear the current conversation history and start fresh |
| `/new` | Start a new session (optionally with a different model/persona) |

**Model & Provider**

| Command | Description |
|---|---|
| `/model` | Show current model, then interactively switch model |
| `/model list` | List all configured model aliases |
| `/model add` | Add a new model alias interactively |
| `/model remove <alias>` | Remove a model alias |
| `/provider` | Show current provider status and health |

**Persona / System Prompt**

| Command | Description |
|---|---|
| `/persona` | Show current persona |
| `/persona set <name>` | Switch to a saved persona |
| `/persona new` | Define a new persona for this session |
| `/persona list` | List all saved personas |
| `/persona save <name>` | Save the current session's persona |
| `/persona clear` | Remove persona for this session (general assistant mode) |

**History & Sessions**

| Command | Description |
|---|---|
| `/history` | List recent sessions |
| `/history open <id>` | Resume a previous session |
| `/history search <query>` | Search session history |
| `/export` | Export current session |

**Keys & Credentials**

| Command | Description |
|---|---|
| `/keys list` | List configured providers and key status |
| `/keys add <provider>` | Add a new API key |
| `/keys update <provider>` | Update an existing key |
| `/keys delete <provider>` | Delete a key |
| `/keys test <provider>` | Test connectivity for a provider |

**Files & Input**

| Command | Description |
|---|---|
| `/file <path>` | Attach a file to the next message |
| `/image <path>` | Attach an image (for multimodal models) |
| `/files` | Show files attached to the current session |

**Web Search & Agent**

| Command | Description |
|---|---|
| `/search on` | Enable web search for all responses this session |
| `/search off` | Disable web search |
| `/search <query>` | Run a one-off web search and show results |

**Theme & UI**

| Command | Description |
|---|---|
| `/theme` | Show current theme and switch interactively |
| `/theme <name>` | Switch to a specific theme (midnight/aurora/ember/arctic) |

**Plugin Management**

| Command | Description |
|---|---|
| `/plugins` | List installed plugins |
| `/plugins install <name>` | Install a plugin |
| `/plugins remove <name>` | Remove a plugin |
| `/plugins info <name>` | Show plugin details |

---

## 11. File Input & Multimodal Support

### 11.1 Text File Input (Context Injection)

Users can send any text-based file as context to the LLM. When a file is attached, its contents are read and injected into the conversation as context. Supported file types include:

- Source code files (`.py`, `.js`, `.ts`, `.java`, `.go`, `.rs`, `.cpp`, `.c`, etc.)
- Data files (`.json`, `.yaml`, `.csv`, `.xml`, `.toml`)
- Documentation (`.md`, `.txt`, `.rst`)
- Configuration files (`.env`, `.ini`, `.cfg`)
- Log files (`.log`)

Files are injected with a clear delimiter and filename label so the LLM knows the source. Long files are handled gracefully — if a file exceeds available context space, Anythink warns the user and asks how to proceed (truncate, chunk, or summarize first).

### 11.2 Image Input (Multimodal)

For providers and models that support multimodal input (e.g., Gemini, GPT-4o, Claude), users can attach images. The image is sent as base64 to the provider's API alongside the user's text prompt. Supported image formats: PNG, JPEG, WEBP, GIF. When an image is attached, a thumbnail indicator is shown in the chat interface.

When a non-multimodal model is active and the user tries to attach an image, Anythink displays a warning: *"The current model (X) does not support image input. Please switch to a multimodal model."* — and lists which of the user's aliases are multimodal-capable.

### 11.3 File Attachment in Chat

Files can be attached using the `/file` or `/image` slash commands, or by dragging and dropping a file path inline in the input. Attached files are shown as labeled indicators in the chat before submission:

```
 📎 Attached: main.py (4.2 KB, Python)
 🖼 Attached: diagram.png (1.1 MB, Image)
```

---

## 12. Agentic Web Search

### 12.1 Web Search as an Agent Tool

Anythink integrates web search as an **agentic tool** — meaning the AI model can decide on its own when to trigger a web search in order to answer a question accurately, in addition to the user being able to explicitly trigger searches.

When web search is enabled (via `/search on` or globally in config), the AI is informed of its search capability via the system prompt. The model then autonomously calls the search tool when it determines the information may be outdated or requires real-world lookup.

### 12.2 Search Flow Display

When a web search is triggered (either by the user or the AI agent), the terminal shows a clear, non-intrusive search status:

```
 🔍 Searching the web: "latest Python 3.13 features"...
 ✓ Found 5 sources — summarizing...
```

After the search, the AI responds with its synthesis of the results. Source URLs are listed at the bottom of the response in a compact references block.

### 12.3 Search Provider

Web search uses a pluggable search backend. The default implementation uses a search API (e.g., SerpAPI, Brave Search API, or DuckDuckGo). The search provider is configurable in the app config, and like LLM providers, additional search backends can be added via the plugin system.

### 12.4 Search in Chat Mode

Web search in Anythink V1 is **chat-integrated**, not a standalone mode. The AI remains in a conversational flow and search results are seamlessly woven into responses. There is no "web browsing mode" in V1 — that deeper agentic capability (clicking links, navigating pages) is reserved for a future version.

---

## 13. Plugin Architecture

### 13.1 Design Philosophy

Anythink's plugin system is designed so that **the core application code is never modified** to add new capabilities. Every extension point — new LLM providers, new search backends, new slash commands, new file handlers — is implemented as a plugin.

### 13.2 Plugin Types

| Plugin Type | What It Adds |
|---|---|
| **LLM Provider Plugin** | A new LLM provider with its own API/auth/streaming |
| **Search Provider Plugin** | A new web search backend |
| **File Handler Plugin** | Support for a new file type (e.g., PDF reader, DOCX extractor) |
| **Slash Command Plugin** | New `/commands` added to the command registry |
| **Output Formatter Plugin** | Custom response rendering (e.g., different markdown styles) |
| **Tool Plugin** | New agentic tools the LLM can call (e.g., code execution, calculator) |

### 13.3 Plugin Discovery & Registry

Plugins are discovered automatically using Python's **entry points** system (the standard PyPI-compatible plugin mechanism). A plugin developer publishes their plugin as a separate PyPI package (e.g., `anythink-provider-anthropic`). When installed via pip, Anythink detects it automatically on next startup — no config editing required.

### 13.4 Plugin Management

Users manage plugins entirely from within Anythink:

- `/plugins` — lists all installed and active plugins
- `/plugins install <name>` — installs a plugin package from PyPI
- `/plugins remove <name>` — uninstalls a plugin
- A plugin registry (community list) will be maintained to make discovery easy.

### 13.5 Plugin Safety

Plugins run in the same process as Anythink. A future version may introduce a sandboxed execution model. For now, plugins are expected to be trusted (sourced from PyPI with standard community vetting). Plugin metadata (name, version, author, permissions) is displayed before installation.

---

## 14. Configuration & Storage

### 14.1 XDG Base Directory Standard

All Anythink data follows the XDG Base Directory Specification. Files are never written to the installation directory or the current working directory.

| Data Type | Location |
|---|---|
| Main config file | `$XDG_CONFIG_HOME/anythink/config.yaml` (default: `~/.config/anythink/config.yaml`) |
| Model alias registry | `$XDG_CONFIG_HOME/anythink/models.yaml` |
| Persona library | `$XDG_CONFIG_HOME/anythink/personas.yaml` |
| Plugin registry | `$XDG_CONFIG_HOME/anythink/plugins.yaml` |
| Session history files | `$XDG_DATA_HOME/anythink/sessions/` (default: `~/.local/share/anythink/sessions/`) |
| Logs | `$XDG_STATE_HOME/anythink/logs/` (default: `~/.local/state/anythink/logs/`) |
| Cache (model metadata, etc.) | `$XDG_CACHE_HOME/anythink/` (default: `~/.cache/anythink/`) |

### 14.2 Main Config File Contents

The main `config.yaml` stores:

- Default model alias
- Active theme
- Whether web search is enabled by default
- Context window warning thresholds
- Session auto-save toggle
- Local LLM server host URLs and ports
- Search provider configuration
- Plugin-specific settings (each plugin gets its own namespace in the config)

The config file is human-readable and editable by hand, with comments explaining each field. Anythink validates the config on startup and reports any invalid entries clearly.

---

## 15. First-Run Setup Wizard

The first time a user runs `anythink` after installing it via pip, an interactive setup wizard runs automatically. It is styled in Anythink's default Midnight theme and uses the ASCII logo.

### 15.1 Wizard Steps

**Step 1 — Welcome**
Displays the Anythink logo, name, version, and a brief welcome message explaining what the wizard will do.

**Step 2 — Theme Selection**
Shows a preview sample of each of the 4 themes and asks the user to select their preferred one.

**Step 3 — Provider Selection**
Presents an interactive list of all supported LLM providers. User selects which one to configure first. They can configure more providers later via `anythink keys add`.

**Step 4 — API Key Entry**
If a cloud provider was selected, asks for the API key. Input is masked. The key is validated with a live test call before saving. On success: ✓ confirmation. On failure: error explanation and retry option.

If a local provider was selected (Ollama/LM Studio/llama.cpp), asks for the server URL and port instead, and tests connectivity.

**Step 5 — Model Alias Setup**
Fetches available models for the selected provider (or asks for a model string for local). Prompts the user to select a model and give it their personal alias name.

**Step 6 — Default Model Confirmation**
Confirms the chosen model alias as the startup default.

**Step 7 — Web Search Setup**
Asks if the user wants to enable web search. If yes, asks for the search API key and tests it.

**Step 8 — Ready**
Displays a summary of configured settings and launches directly into the chat session.

---

## 16. PyPI Distribution & Open Source

### 16.1 Package Name

The PyPI package is published as `anythink`. Installation is:

```
pip install anythink
```

The CLI command after installation is `anythink`.

### 16.2 Open Source License

Anythink is released under the **MIT License** — permissive, widely compatible with the open-source ecosystem, and appropriate for a tool that encourages third-party plugins and contributions.

### 16.3 Repository Structure

The project is hosted on GitHub. The repository is structured as a standard Python project with:

- A well-written `README.md` with screenshots, installation instructions, and quick start
- `CONTRIBUTING.md` with contribution guidelines
- `CHANGELOG.md` tracking all version changes
- `LICENSE` file
- `pyproject.toml` for all build metadata, dependencies, and entry points
- Clear separation of source code under `src/anythink/`

### 16.4 Versioning

Anythink follows **Semantic Versioning (SemVer)** — `MAJOR.MINOR.PATCH`. Breaking changes bump MAJOR, new features bump MINOR, bug fixes bump PATCH.

### 16.5 Dependencies Philosophy

Core dependencies are kept minimal and well-maintained to avoid dependency bloat. Provider-specific dependencies (e.g., the Groq SDK, Google GenerativeAI SDK) are optional extras installable per provider:

```
pip install anythink[groq]
pip install anythink[gemini]
pip install anythink[ollama]
pip install anythink[all]    # installs all provider SDKs
```

---

## 17. Testing & CI Pipeline

### 17.1 Test Framework

All tests are written using **pytest**. The test suite covers:

- Unit tests for each LLM provider adapter
- Unit tests for the model alias registry
- Unit tests for the context window tracking logic
- Unit tests for the slash command parser and registry
- Integration tests for the chat loop with mocked provider responses
- Integration tests for file attachment and content injection
- Integration tests for web search tool (with mocked search API)
- Plugin system tests for discovery and loading
- Setup wizard tests
- Key management tests (with mocked keychain)

### 17.2 Test Coverage

A minimum **80% code coverage** is enforced. Coverage reports are generated on every CI run.

### 17.3 GitHub Actions CI Pipeline

The CI pipeline runs on every pull request and push to `main`. The pipeline includes:

| Stage | What It Does |
|---|---|
| **Lint** | Runs `ruff` for linting and `black` for formatting checks |
| **Type Check** | Runs `mypy` for static type checking |
| **Test** | Runs the full pytest suite on Python 3.11, 3.12, and 3.13 |
| **Coverage** | Generates and uploads coverage report |
| **Security Scan** | Runs `bandit` for security vulnerability scanning |
| **Build** | Builds the PyPI distribution package (`python -m build`) |
| **Publish** | On tagged releases, automatically publishes to PyPI |

---

## 18. Future Roadmap

The following features are planned for future versions and are designed into the architecture from day one — even if not implemented initially.

| Feature | Description | Priority |
|---|---|---|
| **RAG (Retrieval-Augmented Generation)** | Index a local codebase or document folder into a vector store. The AI can then query it for long-term project context beyond the context window. | High — Next Major Feature |
| **Deep Agentic Web Browsing** | Beyond search: the AI can navigate web pages, click links, extract structured data, and summarize full pages. | Medium |
| **Code Execution Tool** | Allow the AI to write and execute Python code in a sandboxed environment and return results to the conversation. | Medium |
| **Multi-File Project Context** | Attach an entire project directory as context, with smart chunking, relevance ranking, and token-efficient injection. | High |
| **Conversation Branching** | Allow users to branch from any point in a session and explore alternative responses, like a conversation tree. | Medium |
| **TUI Dashboard Mode** | A richer terminal UI mode with side panels — session list on the left, chat in the center, model stats on the right. | Low |
| **Voice Input** | Accept voice input via microphone using a local speech-to-text model (e.g., Whisper). | Low |
| **Plugin Marketplace** | A curated community registry of Anythink plugins, browseable from within the app. | Medium |
| **Team Sharing** | Share session histories and persona configs across a team via a simple sync mechanism. | Low |
| **MCP (Model Context Protocol) Support** | Support for connecting to MCP servers, enabling a rich ecosystem of external tool integrations. | Medium |

---

*Anythink — Think anything. Ask anything.*

*Version described: 0.1.0 (V1 — Initial Release Scope)*
*Document last updated: June 2025*
