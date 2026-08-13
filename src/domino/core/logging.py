"""Context-aware logging for Domino.

A thin wrapper over the standard library's :mod:`logging` that stamps every
record with the current correlation id and the name of the object doing the
logging. Use cases, event handlers and aggregate roots expose it as
``self.log`` (they inherit :class:`LoggerMixin`)::

    self.log.info("order confirmed")
    # -> "[Order] [cid=8f3e…] order confirmed" on the "domino" logger

The correlation id and context are also attached to the record as
``correlation_id`` and ``domino_context`` fields, ready for structured handlers.

Domino never configures logging itself (no handlers, no levels) — that is the
application's job. Turn it on with, e.g., ``logging.basicConfig(level="INFO")``.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from functools import cache
from typing import Any

from domino.core.correlation import get_correlation_id

BASE_LOGGER_NAME = "domino"


class DominoLogger(logging.LoggerAdapter):
    """Logging adapter that injects the correlation id and a context label.

    The label is usually the class doing the logging (see :class:`LoggerMixin`),
    so a log line always says who emitted it and which operation it belongs to.
    """

    def __init__(self, logger: logging.Logger, context: str) -> None:
        super().__init__(logger, {})
        self.context = context

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        correlation_id = get_correlation_id()
        prefix = f"[{self.context}]"
        if correlation_id is not None:
            prefix = f"{prefix} [cid={correlation_id}]"
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("correlation_id", correlation_id)
        extra.setdefault("domino_context", self.context)
        return f"{prefix} {msg}", kwargs


@cache
def get_logger(context: str) -> DominoLogger:
    """Return the Domino logger bound to ``context`` (cached per label)."""
    return DominoLogger(logging.getLogger(BASE_LOGGER_NAME), context)


class LoggerMixin:
    """Adds ``self.log``: a Domino logger bound to the instance's class name.

    Mix it into your own classes (a domain service, a repository) to get the
    same contextual logger that use cases, handlers and aggregates already have.
    """

    __slots__ = ()

    @property
    def log(self) -> DominoLogger:
        """A context-aware logger labelled with this instance's class name."""
        return get_logger(type(self).__name__)
