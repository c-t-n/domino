"""Tests for Repository and UnitOfWork."""

from __future__ import annotations

from dataclasses import field
from datetime import UTC, datetime

import pytest

from domino.aggregate.aggregate_root import AggregateRoot
from domino.core.domain_error import DomainStateError
from domino.core.id import DomainId
from domino.events.domain_event import DomainEvent
from domino.events.publisher import EventPublisher
from domino.repository.repository import AsyncRepository, Repository
from domino.uow.unit_of_work import AsyncUnitOfWork, UnitOfWork


class OrderStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class OrderConfirmed(DomainEvent):
    order_id: DomainId


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    status: str = OrderStatus.DRAFT
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def confirm(self) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Only draft orders can be confirmed")
        self.status = OrderStatus.CONFIRMED
        self._touch()
        self._add_event(OrderConfirmed(order_id=self.id))


class InMemoryOrderRepository(Repository[Order]):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)

    def all(self) -> list[Order]:
        return list(self._store.values())


class AsyncInMemoryOrderRepository(AsyncRepository[Order]):
    def __init__(self) -> None:
        self._store: dict[DomainId, Order] = {}

    async def get_by_id(self, id: DomainId) -> Order | None:
        return self._store.get(id)

    async def save(self, aggregate: Order) -> None:
        self._store[aggregate.id] = aggregate

    async def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)


class RecordingBus(EventPublisher):
    """Records every event handed to the bus, in order."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, *events: DomainEvent) -> None:
        self.published.extend(events)


class Tracker:
    """Counts commit/rollback hook invocations."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class TestRepositoryAccess:
    def test_attribute_access(self):
        repo = InMemoryOrderRepository()
        uow = UnitOfWork({"orders": repo})
        assert uow.orders is repo

    def test_repository_method_access(self):
        repo = InMemoryOrderRepository()
        uow = UnitOfWork({"orders": repo})
        assert uow.repository("orders") is repo

    def test_register_adds_repository(self):
        uow = UnitOfWork()
        repo = InMemoryOrderRepository()
        uow.register("orders", repo)
        assert uow.orders is repo

    def test_unknown_repository_attribute_raises(self):
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})
        with pytest.raises(AttributeError):
            _ = uow.customers

    def test_unknown_repository_method_raises(self):
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})
        with pytest.raises(AttributeError):
            uow.repository("customers")


class TestUnitOfWorkTransaction:
    def test_commits_on_clean_exit(self):
        tracker = Tracker()
        repo = InMemoryOrderRepository()
        uow = UnitOfWork(
            {"orders": repo}, commit=tracker.commit, rollback=tracker.rollback
        )

        id = DomainId.empty()

        with uow:
            order = Order()
            order.confirm()
            id = order.id
            uow.orders.save(order)

        assert tracker.commits == 1
        assert tracker.rollbacks == 0
        stored = repo.get_by_id(id)
        assert stored is not None
        assert stored.status == OrderStatus.CONFIRMED

    def test_rolls_back_and_reraises_on_error(self):
        tracker = Tracker()
        repo = InMemoryOrderRepository()
        uow = UnitOfWork(
            {"orders": repo}, commit=tracker.commit, rollback=tracker.rollback
        )

        with pytest.raises(ValueError), uow:
            uow.orders.save(Order())
            raise ValueError("boom")

        assert tracker.commits == 0
        assert tracker.rollbacks == 1

    def test_explicit_commit_is_not_repeated_on_exit(self):
        tracker = Tracker()
        uow = UnitOfWork(commit=tracker.commit, rollback=tracker.rollback)

        with uow:
            uow.commit()

        assert tracker.commits == 1  # not committed again on __exit__

    def test_commit_hook_optional(self):
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})
        with uow:  # no hooks configured -> no-op commit, no error
            uow.orders.save(Order())

    def test_reusable_across_scopes(self):
        tracker = Tracker()
        uow = UnitOfWork(commit=tracker.commit, rollback=tracker.rollback)

        with uow:
            uow.commit()
        with uow:
            uow.commit()

        assert tracker.commits == 2


class TestUnitOfWorkEvents:
    def test_enqueued_events_are_published_after_commit(self):
        bus = RecordingBus()
        uow = UnitOfWork({"orders": InMemoryOrderRepository()}, event_bus=bus)

        with uow:
            order = Order()
            order.confirm()
            uow.orders.save(order)
            uow.enqueue_events(*order.pull_pending_events())
            assert bus.published == []  # nothing leaves before the commit

        assert len(bus.published) == 1
        assert isinstance(bus.published[0], OrderConfirmed)

    def test_events_are_dropped_on_rollback(self):
        bus = RecordingBus()
        uow = UnitOfWork({"orders": InMemoryOrderRepository()}, event_bus=bus)

        with pytest.raises(ValueError), uow:
            order = Order()
            order.confirm()
            uow.enqueue_events(*order.pull_pending_events())
            raise ValueError("boom")

        assert bus.published == []

    def test_queue_is_cleared_between_scopes(self):
        # Regression: the queue used to survive the scope, so every later commit
        # republished the events of the previous one.
        bus = RecordingBus()
        uow = UnitOfWork({"orders": InMemoryOrderRepository()}, event_bus=bus)

        with uow:
            order = Order()
            order.confirm()
            uow.enqueue_events(*order.pull_pending_events())

        with uow:  # nothing enqueued this time
            pass

        assert len(bus.published) == 1

    def test_queue_is_cleared_after_a_rollback(self):
        bus = RecordingBus()
        uow = UnitOfWork(event_bus=bus)

        with pytest.raises(ValueError), uow:
            uow.enqueue_events(OrderConfirmed(order_id=DomainId.generate()))
            raise ValueError("boom")

        with uow:
            pass

        assert bus.published == []  # the rolled-back events never resurface

    def test_events_without_a_bus_are_a_noop(self):
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})

        with uow:  # no event_bus configured -> enqueueing is harmless
            order = Order()
            order.confirm()
            uow.enqueue_events(*order.pull_pending_events())

    def test_private_attribute_falls_back_to_the_instance_dict(self):
        # __getattr__ handles private names itself; calling it directly is the
        # only way to exercise that branch, since Python short-circuits on the
        # instance __dict__ first.
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})
        assert uow.__getattr__("_events") is uow._events

    def test_unknown_private_attribute_raises(self):
        uow = UnitOfWork({"orders": InMemoryOrderRepository()})
        with pytest.raises(AttributeError):
            _ = uow._not_a_repository


class TestAsyncRepositoryAccess:
    def test_attribute_access(self):
        repo = AsyncInMemoryOrderRepository()
        uow = AsyncUnitOfWork({"orders": repo})
        assert uow.orders is repo

    def test_repository_method_access(self):
        repo = AsyncInMemoryOrderRepository()
        uow = AsyncUnitOfWork({"orders": repo})
        assert uow.repository("orders") is repo

    def test_register_adds_repository(self):
        uow = AsyncUnitOfWork()
        repo = AsyncInMemoryOrderRepository()
        uow.register("orders", repo)
        assert uow.orders is repo

    def test_unknown_repository_attribute_raises(self):
        uow = AsyncUnitOfWork({"orders": AsyncInMemoryOrderRepository()})
        with pytest.raises(AttributeError):
            _ = uow.customers

    def test_private_attribute_falls_back_to_the_instance_dict(self):
        # Regression: this branch used to read `self.__dict` (a typo) and blew up
        # with an AttributeError on the unit of work itself.
        uow = AsyncUnitOfWork({"orders": AsyncInMemoryOrderRepository()})
        assert uow.__getattr__("_events") is uow._events

    def test_unknown_private_attribute_raises(self):
        uow = AsyncUnitOfWork({"orders": AsyncInMemoryOrderRepository()})
        with pytest.raises(AttributeError):
            _ = uow._not_a_repository


class TestAsyncUnitOfWorkTransaction:
    async def test_commits_on_clean_exit(self):
        tracker = Tracker()
        repo = AsyncInMemoryOrderRepository()
        uow = AsyncUnitOfWork(
            {"orders": repo}, commit=tracker.commit, rollback=tracker.rollback
        )

        async with uow:
            order = Order()
            order.confirm()
            await uow.orders.save(order)
            oid = order.id

        assert tracker.commits == 1
        assert tracker.rollbacks == 0
        stored = await repo.get_by_id(oid)
        assert stored is not None
        assert stored.status == OrderStatus.CONFIRMED

    async def test_rolls_back_and_reraises_on_error(self):
        tracker = Tracker()
        uow = AsyncUnitOfWork(commit=tracker.commit, rollback=tracker.rollback)

        with pytest.raises(ValueError):
            async with uow:
                raise ValueError("boom")

        assert tracker.commits == 0
        assert tracker.rollbacks == 1

    async def test_explicit_commit_is_not_repeated_on_exit(self):
        tracker = Tracker()
        uow = AsyncUnitOfWork(commit=tracker.commit, rollback=tracker.rollback)

        async with uow:
            await uow.commit()

        assert tracker.commits == 1

    async def test_reusable_across_scopes(self):
        tracker = Tracker()
        uow = AsyncUnitOfWork(commit=tracker.commit, rollback=tracker.rollback)

        async with uow:
            await uow.commit()
        async with uow:
            await uow.commit()

        assert tracker.commits == 2


class TestAsyncUnitOfWorkEvents:
    async def test_enqueued_events_are_published_after_commit(self):
        bus = RecordingBus()
        uow = AsyncUnitOfWork({"orders": AsyncInMemoryOrderRepository()}, event_bus=bus)

        async with uow:
            order = Order()
            order.confirm()
            await uow.orders.save(order)
            uow.enqueue_events(*order.pull_pending_events())
            assert bus.published == []

        assert len(bus.published) == 1
        assert isinstance(bus.published[0], OrderConfirmed)

    async def test_events_are_dropped_on_rollback(self):
        bus = RecordingBus()
        uow = AsyncUnitOfWork(event_bus=bus)

        with pytest.raises(ValueError):
            async with uow:
                order = Order()
                order.confirm()
                uow.enqueue_events(*order.pull_pending_events())
                raise ValueError("boom")

        assert bus.published == []

    async def test_queue_is_cleared_between_scopes(self):
        bus = RecordingBus()
        uow = AsyncUnitOfWork(event_bus=bus)

        async with uow:
            order = Order()
            order.confirm()
            uow.enqueue_events(*order.pull_pending_events())

        async with uow:
            pass

        assert len(bus.published) == 1
