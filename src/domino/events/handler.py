"""EventHandler — reactive handling of domain events.

A handler runs the side effects that are a *consequence* of an event
(reserving stock, sending a mail), not the primary action. Because the
originating transaction has already committed, handlers should not throw;
wrap them in :class:`SafeEventHandler` to turn errors into logs.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable

from domino.events.domain_event import DomainEvent

_logger = logging.getLogger("domino")

ErrorCallback = Callable[[DomainEvent, Exception], None]


class EventHandler(ABC):
    """Base class for domain event handlers.

    Subclasses implement :meth:`handle` and typically guard on ``isinstance``
    to react only to the events they care about.
    """

    @abstractmethod
    def handle(self, event: DomainEvent) -> None:
        """React to a domain event."""


class SafeEventHandler(EventHandler):
    """Wraps a handler so its errors are caught and logged, never propagated."""

    def __init__(
        self, handler: EventHandler, on_error: ErrorCallback | None = None
    ) -> None:
        self._handler = handler
        self._on_error = on_error or self._log_error

    def handle(self, event: DomainEvent) -> None:
        try:
            self._handler.handle(event)
        except Exception as error:
            self._on_error(event, error)

    @staticmethod
    def _log_error(event: DomainEvent, error: Exception) -> None:
        _logger.error(
            "Error handling %s (%s): %s",
            event.event_name,
            event.event_id,
            error,
            exc_info=error,
        )
