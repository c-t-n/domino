"""Turn request query parameters into Domino specifications.

For ``list`` endpoints backed by
:class:`~domino.integrations.sqlalchemy.AsyncFilterable`, translate a whitelisted
set of query parameters into specifications::

    ?status=confirmed&priority__ge=5&status__in=confirmed,shipped&ref__like=AC-%

The operator is an optional ``__op`` suffix on the parameter name (``eq`` when
omitted). ``fields`` both whitelists the filterable attributes — anything not
listed (``limit``, ``offset``, ``sort``, …) is ignored — and converts each raw
string value to the attribute's type.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import Request
from starlette.datastructures import QueryParams

from domino.core.domain_error import DomainValidationError
from domino.core.specification import (
    Specification,
    eq,
    ge,
    gt,
    in_,
    le,
    like,
    lt,
    ne,
)

_BUILDERS: dict[str, Callable[[str, Any], Specification[Any]]] = {
    "eq": eq,
    "ne": ne,
    "lt": lt,
    "le": le,
    "gt": gt,
    "ge": ge,
}

Converter = Callable[[str], Any]


def specifications_from_query(
    params: QueryParams | Mapping[str, str],
    fields: Mapping[str, Converter],
) -> list[Specification[Any]]:
    """Build specifications from query parameters against a field whitelist.

    ``fields`` maps an allowed attribute name to a converter (``str``, ``int``,
    ``Decimal``, …). Parameters for other fields are skipped. A whitelisted field
    with an unknown operator raises :class:`DomainValidationError` (a 422 through
    the installed handlers).
    """
    items = params.multi_items() if isinstance(params, QueryParams) else params.items()
    specs: list[Specification[Any]] = []
    for key, raw in items:
        name, _, op = key.partition("__")
        if name not in fields:
            continue
        convert = fields[name]
        op = op or "eq"
        if op == "in":
            specs.append(in_(name, [convert(v) for v in raw.split(",")]))
        elif op == "like":
            specs.append(like(name, raw))
        elif op in _BUILDERS:
            specs.append(_BUILDERS[op](name, convert(raw)))
        else:
            raise DomainValidationError(
                f"unsupported filter operator {op!r} on field {name!r}"
            )
    return specs


def query_filter(
    fields: Mapping[str, Converter],
) -> Callable[[Request], list[Specification[Any]]]:
    """Build a FastAPI dependency yielding specs from the request query params.

    Usage::

        Filters = Annotated[
            list, Depends(query_filter({"status": str, "priority": int}))
        ]

        @app.get("/orders")
        async def list_orders(specs: Filters, uow: UnitOfWorkDep):
            async with uow:
                return await uow.orders.list(*specs)
    """

    def dependency(request: Request) -> list[Specification[Any]]:
        return specifications_from_query(request.query_params, fields)

    return dependency
