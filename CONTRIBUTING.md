# Contributing to Anythink

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/dhineshtheprogrammer/anythink_ai
cd anythink_ai
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Style

- **Ruff** for linting: `ruff check src/`
- **Black** for formatting: `black src/ tests/`
- **Mypy** for type checking: `mypy src/anythink`

## Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests
4. Ensure all CI checks pass
5. Open a pull request

## Plugin Development

See the documentation on creating Anythink plugins (provider, search backend, slash command, file handler, or tool plugins) via Python entry points.
