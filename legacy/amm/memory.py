"""AMM Phase 5 — Memory Backend Interface

Abstracts ChromaDB behind a MemoryBackend interface so it can be
swapped to Qdrant cloud or Supabase pgvector when needed.

Currently wraps local ChromaDB (already in the stack via CrewAI memory=True).

To swap backend:
  export AMM_MEMORY_BACKEND=qdrant   # or pgvector
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .config import AMM_MEMORY_BACKEND, AMM_WORKSPACE


# ─────────────────────────────────────────────────────────────────────────────
# ABSTRACT INTERFACE
# ─────────────────────────────────────────────────────────────────────────────

class MemoryBackend(ABC):
    """Abstract interface for vector memory storage."""

    @abstractmethod
    def store(self, key: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        """Store an embedding with metadata."""
        ...

    @abstractmethod
    def query(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        """Query for similar embeddings. Returns list of {key, metadata, score}."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete an entry by key."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# CHROMA BACKEND — already in the stack, local, free
# ─────────────────────────────────────────────────────────────────────────────

class ChromaMemoryBackend(MemoryBackend):
    """Local ChromaDB backend — already used by CrewAI memory=True."""

    def __init__(self, collection_name: str = "amm_memory"):
        self._collection = None
        try:
            import chromadb

            db_path = AMM_WORKSPACE.parent / "chroma_db"
            db_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(db_path))
            self._collection = self._client.get_or_create_collection(collection_name)
        except ImportError:
            print("[MEMORY] ChromaDB not installed — memory operations will be no-ops")
        except Exception as e:
            print(f"[MEMORY] ChromaDB init failed: {e} — memory disabled")

    def store(self, key: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        if not self._collection:
            return
        self._collection.upsert(
            ids=[key],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def query(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        if not self._collection:
            return []
        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
            )
        except Exception:
            return []

        output = []
        ids = results.get("ids", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, key in enumerate(ids):
            output.append({
                "key": key,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "score": distances[i] if i < len(distances) else 0.0,
            })
        return output

    def delete(self, key: str) -> None:
        if not self._collection:
            return
        try:
            self._collection.delete(ids=[key])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# STUB BACKENDS — future swaps
# ─────────────────────────────────────────────────────────────────────────────

class NoOpMemoryBackend(MemoryBackend):
    """Fallback when no memory backend is available."""

    def store(self, key: str, embedding: list[float], metadata: dict[str, Any]) -> None:
        pass

    def query(self, embedding: list[float], top_k: int = 5) -> list[dict]:
        return []

    def delete(self, key: str) -> None:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY
# ─────────────────────────────────────────────────────────────────────────────

def get_memory_backend(collection_name: str = "amm_memory") -> MemoryBackend:
    """Return the configured memory backend.

    Controlled by AMM_MEMORY_BACKEND env var:
        "chroma" (default) — local ChromaDB
        "noop" — no-op (testing)
        Future: "qdrant", "pgvector"
    """
    if AMM_MEMORY_BACKEND == "chroma":
        return ChromaMemoryBackend(collection_name)
    if AMM_MEMORY_BACKEND == "noop":
        return NoOpMemoryBackend()
    print(f"[MEMORY] Unknown backend '{AMM_MEMORY_BACKEND}' — falling back to no-op")
    return NoOpMemoryBackend()
