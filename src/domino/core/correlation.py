"""Ambient correlation id, propagated automatically via ``contextvars``.

A correlation id ties together everything that happens while handling one
request or message, so a whole causal chain can be traced across logs, events
and bounded contexts. It lives in a :class:`contextvars.ContextVar`, so it
flows through the call stack (and across ``await``) on its own — application
code, services and aggregates never have to pass it around.

A :class:`~domino.application.use_case.UseCase` opens a scope for you around
every ``execute`` call, so in practice you only read the value::

    with correlation_scope() as cid:   # a use case does this automatically
        ...                            # every DomainEvent here captures `cid`
        current = get_correlation_id()  # == cid

Open a scope yourself only at other boundaries (web middleware, a message
consumer, a background job), passing an upstream id to continue its trace.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from domino.core.config import get_config

_correlation_id: ContextVar[str | None] = ContextVar(
    "domino_correlation_id", default=None
)


def new_correlation_id() -> str:
    """Generate a fresh correlation id (see :func:`~domino.core.config.configure`)."""
    return get_config().correlation_id_factory()


def get_correlation_id() -> str | None:
    """Return the correlation id in scope, or ``None`` if none is active."""
    return _correlation_id.get()


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Run a block under a correlation id, generating one if not given.

    Pass the id received from upstream to continue an existing trace, or omit
    it to start a new one. Nesting is safe: the previous value is restored on
    exit, so an inner scope never leaks into the outer one.
    """
    cid = correlation_id or new_correlation_id()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)
