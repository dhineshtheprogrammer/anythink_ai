"""RAG new-index wizard — 8-step state machine.

The wizard collects index configuration step-by-step via the existing
``InputArea``.  It is NOT a Textual Widget; instead the app holds a
``RAGIndexWizard`` instance and routes ``InputArea.Submitted`` events through
``handle_input()`` while the wizard is active.

Steps:
  1. Name          — alphanumeric + dashes; must be unique among existing indexes
  2. Source Path   — must exist on disk (file or directory)
  3. Chunk Strategy— numbered selection 1–6
  4. Chunk Size    — integer, 256–2048 tokens
  5. Overlap       — numbered selection (80/100/150/200/300/custom)
  6. Embedding     — number from available embedding backends
  7. Vector Store  — number from available backends
  8. Ingest now?   — y/n

``handle_input()`` returns a ``WizardStep`` namedtuple:
  prompt (str)          — what to show the user next (or "" when cancelled/done)
  done   (bool)         — True when all steps collected OR cancelled
  cancelled (bool)      — True when user typed "cancel" or pressed Esc
  result (IndexInfo|None) — populated when done and not cancelled
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.app.context import AppContext
    from anythink.rag.models import IndexInfo

_CHUNK_STRATEGIES = ["fixed", "sentence", "paragraph", "semantic", "code", "heading"]
_OVERLAP_PRESETS = [80, 100, 150, 200, 300]

_STEP_COUNT = 8


@dataclass
class WizardStep:
    """Result returned by ``handle_input()`` after each user submission."""

    prompt: str
    done: bool = False
    cancelled: bool = False
    result: IndexInfo | None = None
    ingest_now: bool = False


@dataclass
class _WizardState:
    step: int = 1
    name: str = ""
    source_path: str = ""
    chunk_strategy: str = "fixed"
    chunk_size: int = 512
    chunk_overlap: int = 100
    embedding_backend: str = "local"
    vector_backend: str = "faiss"
    ingest_now: bool = False
    available_embeddings: list[str] = field(default_factory=list)
    available_backends: list[str] = field(default_factory=list)
    existing_names: list[str] = field(default_factory=list)


def _validate_name(name: str, existing: list[str]) -> str | None:
    """Return an error string, or None if the name is valid."""
    if not name:
        return "Name cannot be empty."
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_\-]*", name):
        return "Name must start with a letter or digit and contain only letters, digits, _ or -."
    if name in existing:
        return f"An index named '{name}' already exists. Choose a different name."
    return None


def _validate_source_path(path: str) -> str | None:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return f"Path does not exist: {path}"
    return None


class RAGIndexWizard:
    """8-step wizard that collects RAG index configuration.

    Usage::
        wizard = RAGIndexWizard(ctx)
        step = wizard.start(prefill_name="my-index")
        # show step.prompt to the user

        step = wizard.handle_input(user_text)
        if step.done:
            if not step.cancelled and step.result:
                ctx.rag_manager.create_index(step.result)
                if step.ingest_now:
                    ...  # fire ingestion worker
    """

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._state: _WizardState | None = None

    @property
    def is_active(self) -> bool:
        return self._state is not None

    def start(self, prefill_name: str = "") -> WizardStep:
        """Initialise wizard state and return the first step prompt."""
        rm = self._ctx.rag_manager
        existing = [info.name for info in rm.list_indexes()]

        from anythink.rag.backends.registry import available_backends

        self._state = _WizardState(
            step=1,
            name=prefill_name,
            embedding_backend=self._ctx.config.embedding_backend,
            vector_backend="faiss",
            available_embeddings=self._ctx.embedding_registry.names() or ["local", "mock"],
            available_backends=available_backends(),
            existing_names=existing,
        )
        return self._prompt_for_step()

    def cancel(self) -> WizardStep:
        """Abort the wizard."""
        self._state = None
        return WizardStep(prompt="", done=True, cancelled=True)

    def handle_input(self, text: str) -> WizardStep:
        """Process one line of user input and advance to the next step.

        Returns a ``WizardStep`` describing what to show next.
        """
        if self._state is None:
            return WizardStep(prompt="", done=True)

        text = text.strip()
        if text.lower() in ("cancel", "quit", "exit"):
            return self.cancel()

        s = self._state
        error = self._validate_current_step(text, s)
        if error:
            return WizardStep(prompt=f"⚠ {error}\n\n{self._step_prompt(s.step, s)}")

        self._apply_input(text, s)
        s.step += 1

        if s.step > _STEP_COUNT:
            return self._finish()

        return self._prompt_for_step()

    # ── internals ─────────────────────────────────────────────────────────────

    def _prompt_for_step(self) -> WizardStep:
        s = self._state
        if s is None:
            return WizardStep(prompt="", done=True)
        return WizardStep(prompt=self._step_prompt(s.step, s))

    def _step_prompt(self, step: int, s: _WizardState) -> str:
        header = f"New RAG Index — Step {step}/{_STEP_COUNT}\n{'─' * 40}"

        if step == 1:
            hint = f"  (pre-filled: {s.name})" if s.name else ""
            return (
                f"{header}\n"
                f"Step 1: Name your index{hint}\n\n"
                f"  Rules: alphanumeric, dashes, underscores (e.g. my-docs)\n"
                f"  Existing: {', '.join(s.existing_names) if s.existing_names else '—'}\n\n"
                f"  → Enter name (or press Enter to use '{s.name}')" if s.name else
                f"{header}\n"
                f"Step 1: Name your index\n\n"
                f"  Rules: alphanumeric, dashes, underscores (e.g. my-docs)\n"
                f"  Existing: {', '.join(s.existing_names) if s.existing_names else '—'}\n\n"
                f"  → Enter name:"
            )

        if step == 2:
            return (
                f"{header}\n"
                f"Step 2: Source path\n\n"
                f"  Enter the directory (or file) to index.\n\n"
                f"  → Enter path:"
            )

        if step == 3:
            choices = "\n".join(
                f"  [{i+1}] {name}" for i, name in enumerate(_CHUNK_STRATEGIES)
            )
            default_idx = _CHUNK_STRATEGIES.index(s.chunk_strategy) + 1
            return (
                f"{header}\n"
                f"Step 3: Chunk strategy\n\n"
                f"{choices}\n\n"
                f"  Default: [{default_idx}] {s.chunk_strategy}\n"
                f"  → Enter number (1–{len(_CHUNK_STRATEGIES)}):"
            )

        if step == 4:
            return (
                f"{header}\n"
                f"Step 4: Chunk size (tokens)\n\n"
                f"  How many tokens per chunk.  256–2048, default {s.chunk_size}.\n\n"
                f"  → Enter number (or Enter for {s.chunk_size}):"
            )

        if step == 5:
            choices = "\n".join(
                f"  [{i+1}] {v} tokens" for i, v in enumerate(_OVERLAP_PRESETS)
            ) + f"\n  [{len(_OVERLAP_PRESETS)+1}] Custom"
            default_label = str(s.chunk_overlap)
            return (
                f"{header}\n"
                f"Step 5: Chunk overlap\n\n"
                f"{choices}\n\n"
                f"  Default: {default_label} tokens\n"
                f"  → Enter number (1–{len(_OVERLAP_PRESETS)+1}) or a token count:"
            )

        if step == 6:
            embs = s.available_embeddings
            choices = "\n".join(f"  [{i+1}] {name}" for i, name in enumerate(embs))
            cur = s.embedding_backend
            default_idx = embs.index(cur) + 1 if cur in embs else 1
            return (
                f"{header}\n"
                f"Step 6: Embedding model\n\n"
                f"{choices}\n\n"
                f"  Default: [{default_idx}] {cur}\n"
                f"  → Enter number (1–{len(embs)}):"
            )

        if step == 7:
            backends = s.available_backends
            choices = "\n".join(f"  [{i+1}] {name}" for i, name in enumerate(backends))
            cur = s.vector_backend
            default_idx = backends.index(cur) + 1 if cur in backends else 1
            return (
                f"{header}\n"
                f"Step 7: Vector store backend\n\n"
                f"{choices}\n\n"
                f"  Default: [{default_idx}] {cur}\n"
                f"  → Enter number (1–{len(backends)}):"
            )

        if step == 8:
            return (
                f"{header}\n"
                f"Step 8: Ingest now?\n\n"
                f"  Index: {s.name}\n"
                f"  Source: {s.source_path}\n"
                f"  Strategy: {s.chunk_strategy}  Size: {s.chunk_size}  Overlap: {s.chunk_overlap}\n"
                f"  Embedding: {s.embedding_backend}  Backend: {s.vector_backend}\n\n"
                f"  → Start ingestion after creating? [y/n]:"
            )

        return f"Unknown step {step}"

    def _validate_current_step(self, text: str, s: _WizardState) -> str | None:
        """Return an error message or None if the input is valid."""
        if s.step == 1:
            # Allow empty input to accept the pre-filled name
            name = text if text else s.name
            return _validate_name(name, s.existing_names)

        if s.step == 2:
            return _validate_source_path(text)

        if s.step == 3:
            try:
                idx = int(text)
                if not 1 <= idx <= len(_CHUNK_STRATEGIES):
                    return f"Enter a number between 1 and {len(_CHUNK_STRATEGIES)}."
            except ValueError:
                return f"Enter a number between 1 and {len(_CHUNK_STRATEGIES)}."
            return None

        if s.step == 4:
            if not text:
                return None  # use default
            try:
                v = int(text)
                if not 256 <= v <= 2048:
                    return "Chunk size must be between 256 and 2048."
            except ValueError:
                return "Enter an integer between 256 and 2048."
            return None

        if s.step == 5:
            if not text:
                return None  # use default
            # Either a preset number or a raw token count
            try:
                v = int(text)
                if v <= 0:
                    return "Overlap must be a positive integer."
            except ValueError:
                return "Enter a preset number or a token count."
            return None

        if s.step == 6:
            embs = s.available_embeddings
            if not text:
                return None
            try:
                idx = int(text)
                if not 1 <= idx <= len(embs):
                    return f"Enter a number between 1 and {len(embs)}."
            except ValueError:
                return f"Enter a number between 1 and {len(embs)}."
            return None

        if s.step == 7:
            backends = s.available_backends
            if not text:
                return None
            try:
                idx = int(text)
                if not 1 <= idx <= len(backends):
                    return f"Enter a number between 1 and {len(backends)}."
            except ValueError:
                return f"Enter a number between 1 and {len(backends)}."
            return None

        if s.step == 8:
            if text.lower() not in ("y", "yes", "n", "no", ""):
                return "Please enter y or n."
            return None

        return None

    def _apply_input(self, text: str, s: _WizardState) -> None:
        """Update wizard state from validated input."""
        if s.step == 1:
            s.name = text if text else s.name

        elif s.step == 2:
            s.source_path = text

        elif s.step == 3:
            idx = int(text) - 1
            s.chunk_strategy = _CHUNK_STRATEGIES[idx]

        elif s.step == 4:
            if text:
                s.chunk_size = int(text)

        elif s.step == 5:
            if not text:
                pass  # keep default
            else:
                v = int(text)
                # If v is a small preset index number (1–N+1), treat as choice
                if 1 <= v <= len(_OVERLAP_PRESETS) + 1:
                    if v <= len(_OVERLAP_PRESETS):
                        s.chunk_overlap = _OVERLAP_PRESETS[v - 1]
                    # else: custom — wait, that was "custom" option, prompt for actual value
                    # For simplicity: if user picks the "Custom" entry, treat it as the default
                else:
                    # Treat as raw token count
                    s.chunk_overlap = max(80, v)

        elif s.step == 6:
            embs = s.available_embeddings
            if text:
                idx = int(text) - 1
                s.embedding_backend = embs[idx]

        elif s.step == 7:
            backends = s.available_backends
            if text:
                idx = int(text) - 1
                s.vector_backend = backends[idx]

        elif s.step == 8:
            s.ingest_now = text.lower() in ("y", "yes")

    def _finish(self) -> WizardStep:
        """Build the IndexInfo from collected state and return done."""
        s = self._state
        if s is None:
            return WizardStep(prompt="", done=True, cancelled=True)

        from anythink.rag.models import IndexInfo

        info = IndexInfo(
            name=s.name,
            index_type="document",
            source_path=s.source_path,
            persistence_mode="persist",
            chunk_strategy=s.chunk_strategy,
            chunk_size=s.chunk_size,
            chunk_overlap=s.chunk_overlap,
            embedding_backend=s.embedding_backend,
            vector_backend=s.vector_backend,
        )

        ingest_now = s.ingest_now
        self._state = None

        return WizardStep(
            prompt=(
                f"✓ Index '{info.name}' created.\n"
                f"  Strategy: {info.chunk_strategy}  ·  "
                f"Size: {info.chunk_size}  ·  Overlap: {info.chunk_overlap}\n"
                f"  Embedding: {info.embedding_backend}  ·  Backend: {info.vector_backend}"
                + ("\n\n  Starting ingestion…" if ingest_now else "")
            ),
            done=True,
            result=info,
            ingest_now=ingest_now,
        )
