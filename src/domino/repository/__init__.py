"""Repository pattern — in-memory-like interface for aggregate persistence."""

from domino.repository.repository import AsyncRepository, Repository

__all__ = ["Repository", "AsyncRepository"]
