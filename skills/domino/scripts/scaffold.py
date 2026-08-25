#!/usr/bin/env python3
"""Scaffold a Domino bounded context.

Generates a domain / application / infrastructure package with correct,
decorator-free Domino starter stubs (an aggregate, an event, a command, a use
case and an in-memory repository), ready to flesh out.

Usage:
    python scaffold.py <context_name> [--path DIR] [--aggregate NAME]

Examples:
    python scaffold.py billing
    python scaffold.py catalog --path src --aggregate Product

Existing files are left untouched; only missing ones are created. Standard
library only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Templates use __AGG__ / __agg__ / __CONTEXT__ placeholders (avoids escaping the
# many literal braces in dict/type-hint syntax that f-strings/format would need).

_TEMPLATES: dict[str, str] = {
    "__init__.py": '"""The __CONTEXT__ bounded context."""\n',
    "domain/__init__.py": '"""Domain layer: the model and its rules."""\n',
    "domain/value_objects.py": '''"""Value objects for the __CONTEXT__ context."""

from __future__ import annotations

from domino import DomainValidationError, ValueObject


class Name(ValueObject):
    """Example value object — replace with your own."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise DomainValidationError("name cannot be empty")
''',
    "domain/events.py": '''"""Domain events for the __CONTEXT__ context."""

from __future__ import annotations

from domino import DomainEvent, DomainId


class __AGG__Created(DomainEvent):
    __agg___id: DomainId
    # event_id / occurred_on / correlation_id are inherited and auto-filled.
''',
    "domain/aggregates.py": '''"""Aggregates for the __CONTEXT__ context."""

from __future__ import annotations

from dataclasses import field
from datetime import UTC, datetime

from domino import AggregateRoot, DomainId

from .events import __AGG__Created


class __AGG__(AggregateRoot):
    _id: DomainId = field(default_factory=DomainId.generate)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls) -> "__AGG__":
        instance = cls()
        instance._add_event(__AGG__Created(__agg___id=instance.id))
        return instance
''',
    "application/__init__.py": '"""Application layer: commands and use cases."""\n',
    "application/commands.py": '''"""Commands for the __CONTEXT__ context."""

from __future__ import annotations

from domino import Command


class Create__AGG__Command(Command):
    pass  # add the inputs your use case needs
''',
    "application/use_cases.py": '''"""Use cases for the __CONTEXT__ context."""

from __future__ import annotations

from domino import DomainId, UseCase

from ..domain.aggregates import __AGG__
from .commands import Create__AGG__Command


class Create__AGG__(UseCase[Create__AGG__Command, DomainId]):
    """Wire it with a UnitOfWork holding a "__agg__s" repository.

    The base __init__ takes that unit of work and exposes it as ``self._uow``;
    the caller owns the transaction scope::

        with uow:
            id = Create__AGG__(uow).execute(command)
    """

    def execute(self, command: Create__AGG__Command) -> DomainId:
        self.log.info("creating __agg__")
        repository = self._uow.repository("__agg__s")
        entity = __AGG__.create()
        repository.save(entity)
        self._uow.enqueue_events(*entity.pull_pending_events())
        return entity.id
''',
    "infrastructure/__init__.py": '"""Infrastructure layer: ports made concrete."""\n',
    "infrastructure/repositories.py": '''"""Repositories for __CONTEXT__."""

from __future__ import annotations

from domino import DomainId, Repository

from ..domain.aggregates import __AGG__


class __AGG__Repository(Repository[__AGG__]):
    """In-memory repository — swap for a real store in production."""

    def __init__(self) -> None:
        self._store: dict[DomainId, __AGG__] = {}

    def get_by_id(self, id: DomainId) -> __AGG__ | None:
        return self._store.get(id)

    def save(self, aggregate: __AGG__) -> None:
        self._store[aggregate.id] = aggregate

    def delete(self, id: DomainId) -> None:
        self._store.pop(id, None)
''',
}


def _render(template: str, context: str, aggregate: str) -> str:
    return (
        template.replace("__CONTEXT__", context)
        .replace("__AGG__", aggregate)
        .replace("__agg__", aggregate.lower())
    )


def scaffold(
    context: str, base_path: Path, aggregate: str
) -> tuple[list[Path], list[Path]]:
    """Write the skeleton. Returns (created, skipped) paths."""
    root = base_path / context
    created: list[Path] = []
    skipped: list[Path] = []
    for rel, template in _TEMPLATES.items():
        target = root / rel
        if target.exists():
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_render(template, context, aggregate), encoding="utf-8")
        created.append(target)
    return created, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a Domino bounded context.")
    parser.add_argument("context", help="context/package name, e.g. 'billing'")
    parser.add_argument(
        "--path", default=".", help="directory to create the context in (default: .)"
    )
    parser.add_argument(
        "--aggregate",
        default="Sample",
        help="name of the starter aggregate (default: Sample)",
    )
    args = parser.parse_args()

    if not args.context.isidentifier():
        parser.error(f"context must be a valid Python identifier, got {args.context!r}")
    if not args.aggregate.isidentifier():
        parser.error(f"aggregate must be a valid identifier, got {args.aggregate!r}")

    created, skipped = scaffold(args.context, Path(args.path), args.aggregate)

    for path in created:
        print(f"  created  {path}")
    for path in skipped:
        print(f"  skipped  {path} (exists)")
    print(f"\n{len(created)} file(s) created, {len(skipped)} skipped.")
    if created:
        print(
            f"Next: implement the {args.aggregate} behaviour, then wire "
            f"Create{args.aggregate} with a UnitOfWork holding a "
            f"'{args.aggregate.lower()}s' repository (and an EventBus)."
        )


if __name__ == "__main__":
    main()
