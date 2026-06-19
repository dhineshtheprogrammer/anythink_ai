# Anythink

> Think anything. Ask anything.

**Anythink** is a universal, AI-powered CLI chatbot with a beautiful terminal interface, multi-provider LLM support, and an extensible plugin architecture. Built in Python. Distributed as an open-source PyPI package.

## Features

- **Multi-provider**: Groq, Google Gemini, OpenAI, Anthropic, Mistral, Cohere, Ollama, LM Studio, llama.cpp
- **Beautiful terminal UI**: Rich markdown rendering, real-time token streaming, 4 color themes
- **Model aliases**: Give your models friendly personal names
- **Session management**: Auto-save conversations, resume sessions, search history
- **Slash commands**: 30+ built-in commands for everything from model switching to web search
- **Extensible**: Add new providers, search backends, and slash commands via plugins

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
pip install anythink[all]        # All providers
```

## Quick Start

```bash
anythink          # Start a chat session (runs setup wizard on first run)
anythink --help   # Show help
anythink keys add groq  # Add a Groq API key
anythink model list     # List configured model aliases
```

## License

MIT — see [LICENSE](LICENSE) for details.
