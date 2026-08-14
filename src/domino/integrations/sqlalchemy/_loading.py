"""Eager-loading options that pull a whole aggregate in one async round-trip.

Async SQLAlchemy cannot lazy-load a relationship on attribute access (there is no
greenlet to bridge the implicit IO), so the async repository loads an aggregate's
entire object graph up front. That also matches DDD: a repository returns a whole
aggregate — root plus its internal entities — not a lazily-stitched shell.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import inspect
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.orm.mapper import Mapper


def _walk(mapper: Mapper[Any], loader: Any, seen: frozenset[Mapper[Any]]) -> list[Any]:
    options: list[Any] = []
    for rel in mapper.relationships:
        step = (loader.selectinload if loader else selectinload)(rel.class_attribute)
        options.append(step)
        if rel.mapper not in seen:
            options.extend(_walk(rel.mapper, step, seen | {rel.mapper}))
    return options


def eager_load_options(aggregate_type: type) -> list[ORMOption]:
    """``selectinload`` options covering every relationship of the aggregate.

    Recurses through nested relationships (guarding against cycles), so the full
    aggregate graph is fetched eagerly. Returns an empty list for an aggregate
    with no relationships.
    """
    mapper = cast("Mapper[Any]", inspect(aggregate_type))
    return _walk(mapper, None, frozenset({mapper}))
