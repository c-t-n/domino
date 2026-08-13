"""Central configuration for Domino.

Domino works out of the box, but a few cross-cutting behaviours can be tuned in
one place — most notably how identifiers and correlation ids are generated.
Call :func:`configure` once, at application startup::

    from uuid import uuid4
    from domino import configure

    # 16-char correlation ids instead of a 32-char uuid hex
    configure(correlation_id_factory=lambda: uuid4().hex[:16])

    # or a third-party generator such as NanoID — for domain ids too
    from nanoid import generate
    configure(
        correlation_id_factory=lambda: generate(size=16),
        id_factory=generate,
    )

Settings are process-wide (the *strategy*), while the correlation id itself
stays per-operation (the *value*, carried by a contextvar).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID, uuid4


def _uuid_hex() -> str:
    return uuid4().hex


def _uuid() -> UUID | str:
    return uuid4()


@dataclass(frozen=True)
class DominoConfig:
    """An immutable snapshot of Domino's configurable behaviours.

    Attributes:
        correlation_id_factory: Builds a new correlation id (see
            :func:`~domino.core.correlation.new_correlation_id`).
        id_factory: Builds the raw value wrapped by
            :meth:`~domino.core.id.DomainId.generate`.
    """

    correlation_id_factory: Callable[[], str] = _uuid_hex
    id_factory: Callable[[], UUID | str] = _uuid


_config = DominoConfig()


def get_config() -> DominoConfig:
    """Return the current configuration."""
    return _config


def configure(
    *,
    correlation_id_factory: Callable[[], str] | None = None,
    id_factory: Callable[[], UUID | str] | None = None,
) -> None:
    """Override one or more global settings, at application startup.

    Only the arguments you pass are changed; everything else keeps its value.
    """
    global _config
    config = _config
    if correlation_id_factory is not None:
        config = replace(config, correlation_id_factory=correlation_id_factory)
    if id_factory is not None:
        config = replace(config, id_factory=id_factory)
    _config = config


def reset_config() -> None:
    """Restore the default configuration (mostly useful in tests)."""
    global _config
    _config = DominoConfig()
