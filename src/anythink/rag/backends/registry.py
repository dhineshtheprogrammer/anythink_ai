"""Backend registry — factory functions for vector store backends.

Usage::

    from anythink.rag.backends.registry import (
        get_backend,
        load_store,
        store_exists,
        BACKENDS,
    )

    store = get_backend("faiss")           # empty instance (falls back to pure if unavailable)
    store = load_store("faiss", base_path) # load from disk
    ok = store_exists("faiss", base_path)  # check if persisted data exists

All functions gracefully fall back to the "pure" backend when the requested
backend's optional dependency is not installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anythink.rag.backends.base import BaseVectorStore

# ── Lazy import map ───────────────────────────────────────────────────────────

# Maps backend name → (module, class_name)
_LAZY: dict[str, tuple[str, str]] = {
    "faiss": ("anythink.rag.backends.faiss_store", "FAISSVectorStore"),
    "chroma": ("anythink.rag.backends.chroma_store", "ChromaVectorStore"),
    "lance": ("anythink.rag.backends.lance_store", "LanceVectorStore"),
    "pinecone": ("anythink.rag.backends.pinecone_store", "PineconeVectorStore"),
    "azure": ("anythink.rag.backends.azure_store", "AzureVectorStore"),
}

# Public backend name list (for wizard / settings display)
BACKENDS: list[str] = ["pure", "faiss", "chroma", "lance", "pinecone", "azure"]


# ── Core helpers ──────────────────────────────────────────────────────────────


def get_backend_class(name: str) -> type[BaseVectorStore]:
    """Return the backend class for *name*, falling back to PureVectorStore.

    Imports the backend's module lazily so missing optional deps only raise
    errors when the backend is actually instantiated/used.
    """
    from anythink.rag.backends.pure import PureVectorStore

    if name == "pure":
        return PureVectorStore

    if name in _LAZY:
        import importlib

        module_name, class_name = _LAZY[name]
        try:
            mod = importlib.import_module(module_name)
            return getattr(mod, class_name)
        except (ImportError, AttributeError):
            return PureVectorStore

    return PureVectorStore


def get_backend(name: str) -> BaseVectorStore:
    """Return an **empty** backend instance for *name*.

    Falls back to PureVectorStore if the optional dependency is not installed
    or the backend's ``is_available()`` returns False.
    """
    from anythink.rag.backends.pure import PureVectorStore

    cls = get_backend_class(name)
    instance = cls()

    if hasattr(instance, "is_available") and not instance.is_available():
        return PureVectorStore()

    return instance


def load_store(name: str, base_path: Path) -> BaseVectorStore:
    """Load a persisted backend from *base_path*.

    Falls back to PureVectorStore if the backend is unavailable or no data
    exists at *base_path*.
    """
    from anythink.rag.backends.pure import PureVectorStore

    cls = get_backend_class(name)

    # Check availability before loading (avoids ImportError at load time)
    test = cls()
    if hasattr(test, "is_available") and not test.is_available():
        # Try loading pure as a last resort
        if PureVectorStore.exists(base_path):
            return PureVectorStore.load(base_path)
        return PureVectorStore()

    if cls.exists(base_path):
        return cls.load(base_path)

    # If FAISS/Chroma not found, check legacy pure store (backward compat)
    if name != "pure" and PureVectorStore.exists(base_path):
        return PureVectorStore.load(base_path)

    return cls()  # empty store


def store_exists(name: str, base_path: Path) -> bool:
    """Return True if persisted data for *name* backend exists at *base_path*."""
    from anythink.rag.backends.pure import PureVectorStore

    cls = get_backend_class(name)
    if cls.exists(base_path):
        return True
    # Backward compat: check legacy pure store for any backend type
    return PureVectorStore.exists(base_path)


def is_backend_available(name: str) -> bool:
    """Return True if the backend's optional dependency is installed."""
    if name == "pure":
        return True
    cls = get_backend_class(name)
    if cls.__name__ == "PureVectorStore":
        return False  # fell back — dep not installed
    instance = cls()
    if hasattr(instance, "is_available"):
        return instance.is_available()
    return True


def available_backends() -> list[str]:
    """Return backend names whose optional dependencies are installed."""
    return [name for name in BACKENDS if is_backend_available(name)]
