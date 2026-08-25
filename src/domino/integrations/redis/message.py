"""The wire format shared by the Redis publisher and consumer.

A stream entry keeps the envelope's fields flat rather than burying the whole
thing in one blob: ``XRANGE`` stays readable while debugging, and a consumer can
look at ``event_name`` without decoding the payload.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from domino.events.domain_event import DomainEvent
from domino.events.serialization import EventRegistry, SerializationError

PAYLOAD_FIELD = "payload"


def to_fields(registry: EventRegistry, event: DomainEvent) -> dict[str, str]:
    """The stream entry for an event."""
    envelope = registry.encode(event)
    return {
        "event_name": envelope["event_name"],
        "event_id": envelope["event_id"],
        "occurred_on": envelope["occurred_on"],
        "correlation_id": envelope["correlation_id"] or "",
        PAYLOAD_FIELD: json.dumps(envelope["payload"]),
    }


def to_envelope(fields: Mapping[Any, Any]) -> dict[str, Any]:
    """Rebuild an envelope from a stream entry, whatever the client's decoding.

    ``redis.Redis(decode_responses=False)`` hands back bytes, ``True`` hands back
    str; both are accepted so the client stays the caller's choice.
    """
    decoded = {_text(key): _text(value) for key, value in fields.items()}
    try:
        payload = json.loads(decoded[PAYLOAD_FIELD])
    except KeyError:
        raise SerializationError("stream entry has no 'payload' field") from None
    except json.JSONDecodeError as exc:
        raise SerializationError(f"stream entry payload is not JSON: {exc}") from exc

    return {
        "event_name": decoded.get("event_name"),
        "event_id": decoded.get("event_id"),
        "occurred_on": decoded.get("occurred_on"),
        "correlation_id": decoded.get("correlation_id") or None,
        "payload": payload,
    }


def _text(value: Any) -> Any:
    return value.decode() if isinstance(value, bytes) else value
