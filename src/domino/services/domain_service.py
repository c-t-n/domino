"""DomainService — stateless logic that spans multiple aggregates.

Reach for a domain service when a rule doesn't belong to any single entity or
value object. It is stateless, named after a domain concept, and lives in the
domain layer (no transactions, auth or logging — those belong to a use case).
"""

from __future__ import annotations


class DomainService:
    """Marker base for stateless, cross-aggregate domain services.

    Usage::

        class TransferService(DomainService):
            def __init__(self, accounts: AccountRepository) -> None:
                self._accounts = accounts

            def transfer(self, src: DomainId, dst: DomainId, amount: Money) -> None:
                ...
    """
