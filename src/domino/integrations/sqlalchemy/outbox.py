"""Transactional outbox — events that commit with the data that caused them.

Publishing after a commit leaves a window: if the process dies between the two,
the event is gone and nothing says so. The outbox closes it by writing events to
a table *inside* the same transaction, so rows and events become durable
together or not at all. A relay ships them afterwards::

    outbox = Outbox(registry, metadata=metadata)   # declares the table
    uow = AsyncSqlAlchemyUnitOfWork(session_factory, repos, outbox=outbox)

    async with uow:                       # one transaction
        await uow.orders.save(order)
        uow.enqueue_events(*order.pull_pending_events())
        # the rows and the outbox lines commit together

    relay = AsyncOutboxRelay(session_factory, outbox, publisher=broker)
    await relay.run_once()                # publishes, then marks the lines sent

Delivery is **at-least-once**: a relay that publishes and then crashes before
marking a line will send it again. Consumers deduplicate on ``event_id``, which
the envelope carries.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Select,
    String,
    Table,
    Text,
    Update,
    select,
    update,
)
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from domino.core.logging import get_logger
from domino.events.domain_event import DomainEvent
from domino.events.publisher import AsyncEventPublisher, EventPublisher
from domino.events.serialization import EventRegistry

#: Dialects whose SELECT ... FOR UPDATE supports SKIP LOCKED, so several relays
#: can drain the same table without publishing a line twice.
_SKIP_LOCKED_DIALECTS = frozenset({"postgresql", "mysql", "mariadb", "oracle"})

_logger = get_logger("Outbox")


def outbox_table(metadata: MetaData, name: str = "domino_outbox") -> Table:
    """Declare the outbox table on your metadata, so your migration creates it.

    ``event_id`` is unique: an event that somehow gets staged twice within a
    transaction lands once.
    """
    return Table(
        name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("event_id", String(36), nullable=False, unique=True, index=True),
        Column("event_name", String(255), nullable=False),
        Column("correlation_id", String(64), nullable=True),
        Column("occurred_on", DateTime(timezone=True), nullable=False),
        Column("envelope", Text, nullable=False),
        Column("published_at", DateTime(timezone=True), nullable=True, index=True),
        Column("attempts", Integer, nullable=False, default=0),
        Column("last_error", Text, nullable=True),
    )


class Outbox:
    """The outbox table plus the codec that fills it.

    Holds no connection: it builds statements a unit of work or a relay
    executes, which is what lets one object serve both the sync and the async
    stack.
    """

    def __init__(
        self,
        registry: EventRegistry,
        *,
        metadata: MetaData | None = None,
        table: Table | None = None,
        name: str = "domino_outbox",
    ) -> None:
        if table is None:
            if metadata is None:
                raise ValueError(
                    "pass either metadata= (to declare the table) or table="
                )
            table = outbox_table(metadata, name)
        self.table = table
        self._registry = registry

    # --- writing ------------------------------------------------------------

    def rows_for(self, events: Sequence[DomainEvent]) -> list[dict[str, Any]]:
        """Serialize events into rows ready for insertion."""
        rows = []
        for event in events:
            envelope = self._registry.encode(event)
            rows.append(
                {
                    "event_id": envelope["event_id"],
                    "event_name": envelope["event_name"],
                    "correlation_id": envelope["correlation_id"],
                    "occurred_on": event.occurred_on,
                    "envelope": json.dumps(envelope),
                    "attempts": 0,
                }
            )
        return rows

    # --- reading ------------------------------------------------------------

    def select_unpublished(
        self, limit: int, *, skip_locked: bool = False
    ) -> Select[Any]:
        """The oldest unpublished lines, in the order they were written."""
        statement = (
            select(self.table)
            .where(self.table.c.published_at.is_(None))
            .order_by(self.table.c.id)
            .limit(limit)
        )
        if skip_locked:
            statement = statement.with_for_update(skip_locked=True)
        return statement

    def event_from(self, row: Row[Any]) -> DomainEvent:
        """Rebuild the event a stored line describes."""
        return self._registry.decode(json.loads(row.envelope))

    def mark_published(self, ids: Sequence[int]) -> Update:
        """Mark lines as sent."""
        return (
            update(self.table)
            .where(self.table.c.id.in_(ids))
            .values(published_at=datetime.now(UTC))
        )

    def mark_failed(self, id_: int, error: Exception) -> Update:
        """Record a failed attempt, leaving the line to be retried."""
        return (
            update(self.table)
            .where(self.table.c.id == id_)
            .values(attempts=self.table.c.attempts + 1, last_error=str(error)[:1000])
        )


def _skip_locked_for(bind: Any, requested: bool | None) -> bool:
    """Whether to add SKIP LOCKED, guessing from the dialect when not told."""
    if requested is not None:
        return requested
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    return dialect in _SKIP_LOCKED_DIALECTS


class OutboxRelay:
    """Publishes staged events, then marks them sent.

    One line at a time on purpose: a publisher that fails on the third event of
    a batch must not lose the two before it, nor resend them.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        outbox: Outbox,
        *,
        publisher: EventPublisher,
        batch_size: int = 100,
        skip_locked: bool | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._outbox = outbox
        self._publisher = publisher
        self._batch_size = batch_size
        self._skip_locked = skip_locked

    def run_once(self) -> int:
        """Publish one batch; returns how many events went out."""
        session = self._session_factory()
        try:
            skip_locked = _skip_locked_for(session.get_bind(), self._skip_locked)
            rows = session.execute(
                self._outbox.select_unpublished(
                    self._batch_size, skip_locked=skip_locked
                )
            ).all()

            sent: list[int] = []
            for row in rows:
                try:
                    self._publisher.publish(self._outbox.event_from(row))
                except (Exception, SQLAlchemyError) as error:
                    _logger.error(
                        "outbox line %s (%s) failed to publish: %s",
                        row.id,
                        row.event_name,
                        error,
                    )
                    session.execute(self._outbox.mark_failed(row.id, error))
                    break  # keep the order: stop at the first failure
                sent.append(row.id)

            if sent:
                session.execute(self._outbox.mark_published(sent))
            session.commit()
            return len(sent)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run(self, poll_interval: float = 1.0) -> None:
        """Drain the outbox forever, sleeping when it is empty (Ctrl-C to stop)."""
        while True:
            if self.run_once() == 0:
                time.sleep(poll_interval)


class AsyncOutboxRelay:
    """The ``async`` counterpart of :class:`OutboxRelay`."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        outbox: Outbox,
        *,
        publisher: EventPublisher | AsyncEventPublisher,
        batch_size: int = 100,
        skip_locked: bool | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._outbox = outbox
        self._publisher = publisher
        self._batch_size = batch_size
        self._skip_locked = skip_locked

    async def run_once(self) -> int:
        """Publish one batch; returns how many events went out."""
        session = self._session_factory()
        try:
            skip_locked = _skip_locked_for(session.get_bind(), self._skip_locked)
            result = await session.execute(
                self._outbox.select_unpublished(
                    self._batch_size, skip_locked=skip_locked
                )
            )
            rows = result.all()

            sent: list[int] = []
            for row in rows:
                try:
                    published = self._publisher.publish(self._outbox.event_from(row))
                    if published is not None:
                        await published
                except (Exception, SQLAlchemyError) as error:
                    _logger.error(
                        "outbox line %s (%s) failed to publish: %s",
                        row.id,
                        row.event_name,
                        error,
                    )
                    await session.execute(self._outbox.mark_failed(row.id, error))
                    break
                sent.append(row.id)

            if sent:
                await session.execute(self._outbox.mark_published(sent))
            await session.commit()
            return len(sent)
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def run(self, poll_interval: float = 1.0) -> None:
        """Drain the outbox until cancelled, sleeping when it is empty."""
        while True:
            if await self.run_once() == 0:
                await asyncio.sleep(poll_interval)
