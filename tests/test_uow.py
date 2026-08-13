"""Tests for Repository and UnitOfWork."""

from __future__ import annotations

from dataclasses import field
from datetime import UTC, datetime

import pytest

from domino.aggregate.aggregate_root import AggregateRoot
from domino.core.domain_error import DomainStateError
from domino.core.id import DomainId
from domino.repository.repository import Repository
from domino.uow.unit_of_work import UnitOfWork


class OrderStatus:
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class Order(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    status: str = OrderStatus.DRAFT
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def confirm(self) -> None:
        if self.status != OrderStatus.DRAFT:
            raise DomainStateError("Only draft orders can be confirmed")
        self.status = OrderStatus.CONFIRMED
        self._touch()


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
