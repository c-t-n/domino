"""Infer a repository's aggregate type from its generic base."""

from __future__ import annotations

import typing


def infer_aggregate_type(cls: type, marker: type) -> type | None:
    """Extract ``X`` from a ``marker[X]`` base of ``cls``, if present.

    ``marker`` is the repository base to look for (e.g. ``SqlAlchemyRepository``),
    so a class mixing several generic bases resolves to the aggregate declared on
    the repository base rather than on a sibling mixin.
    """
    for base in getattr(cls, "__orig_bases__", ()):
        origin = typing.get_origin(base)
        if isinstance(origin, type) and issubclass(origin, marker):
            args = typing.get_args(base)
            if args and isinstance(args[0], type):
                return args[0]
    return None
