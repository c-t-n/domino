"""Turn domain events into transport-ready data, and back.

An in-process :class:`~domino.events.bus.EventBus` hands handlers the very
object an aggregate produced. Crossing a process boundary — a broker, an outbox
table, an audit log — needs a stable representation instead, plus a way to find
the class again on the other side. That is what an :class:`EventRegistry` does::

    registry = EventRegistry()
    registry.register(OrderConfirmed)

    envelope = registry.encode(event)
    # {"event_name": "OrderConfirmed", "event_id": "…", "occurred_on": "…",
    #  "correlation_id": "…", "payload": {"order_id": "…", "total": "42.00"}}

    same = registry.decode(envelope)  # an OrderConfirmed again

The envelope keeps ``event_id``, ``occurred_on`` and ``correlation_id`` at the
top level: a consumer needs them to deduplicate and to continue the trace
without decoding the payload first.

``encode``/``decode`` deal in plain dictionaries, so any codec (JSON, msgpack,
Avro) can carry them; :meth:`EventRegistry.encode_json` and
:meth:`EventRegistry.decode_json` are the stdlib-JSON shortcuts.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from domino.core.id import DomainId
from domino.events.domain_event import DomainEvent

#: Envelope keys that carry the base event fields, outside the payload.
_ENVELOPE_FIELDS = ("event_id", "occurred_on", "correlation_id")

_SEQUENCES: dict[Any, Callable[[Iterable[Any]], Any]] = {
    list: list,
    tuple: tuple,
    set: set,
    frozenset: frozenset,
}


class SerializationError(Exception):
    """Raised when an event cannot be encoded or decoded.

    Deliberately *not* a :class:`~domino.core.domain_error.DomainError`: a
    payload that will not round-trip is an infrastructure failure, not a broken
    business rule, and must not be mapped to a 4xx response.
    """


class EventRegistry:
    """Maps event names to their classes, and encodes events to envelopes.

    Registration is explicit: an event you never registered cannot be decoded by
    a consumer, so encoding it would publish a message nobody can read.

    Usage::

        registry = EventRegistry()
        registry.register(OrderConfirmed)
        registry.register(OrderShipped, name="orders.OrderShipped.v2")

    A name defaults to the class name (``event.event_name``). Pass ``name=`` to
    namespace events per bounded context, or to version a payload whose shape
    changed.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, type[DomainEvent]] = {}
        self._by_type: dict[type[DomainEvent], str] = {}
        self._encoders: dict[type, Callable[[Any], Any]] = {}
        self._decoders: dict[type, Callable[[Any], Any]] = {}

    # --- registration -------------------------------------------------------

    def register(
        self, event_type: type[DomainEvent], *, name: str | None = None
    ) -> type[DomainEvent]:
        """Register an event type under ``name`` (its class name by default).

        Returns the type, so it doubles as a class decorator.
        """
        key = name or event_type.__name__
        known = self._by_name.get(key)
        if known is not None and known is not event_type:
            raise SerializationError(
                f"{key!r} is already registered for {known.__name__}; "
                f"pass name= to disambiguate {event_type.__name__}"
            )
        self._by_name[key] = event_type
        self._by_type[event_type] = key
        return event_type

    def register_all(self, event_types: Iterable[type[DomainEvent]]) -> None:
        """Register several event types under their class names."""
        for event_type in event_types:
            self.register(event_type)

    def register_codec(
        self,
        value_type: type,
        encode: Callable[[Any], Any],
        decode: Callable[[Any], Any],
    ) -> None:
        """Teach the registry a value type it doesn't handle out of the box.

        ``encode`` returns something the transport can carry; ``decode`` rebuilds
        the value from it::

            registry.register_codec(IPv4Address, str, IPv4Address)
        """
        self._encoders[value_type] = encode
        self._decoders[value_type] = decode

    def name_for(self, event_type: type[DomainEvent]) -> str:
        """The registered name of an event type."""
        try:
            return self._by_type[event_type]
        except KeyError:
            raise SerializationError(
                f"{event_type.__name__} is not registered; "
                f"call registry.register({event_type.__name__})"
            ) from None

    def type_for(self, name: str) -> type[DomainEvent]:
        """The event type registered under ``name``."""
        try:
            return self._by_name[name]
        except KeyError:
            known = ", ".join(sorted(self._by_name)) or "nothing"
            raise SerializationError(
                f"no event registered as {name!r} (registered: {known})"
            ) from None

    # --- encoding -----------------------------------------------------------

    def encode(self, event: DomainEvent) -> dict[str, Any]:
        """Return the transport envelope for an event."""
        payload = {
            field.name: self._encode_value(getattr(event, field.name))
            for field in dataclasses.fields(event)
            if field.name not in _ENVELOPE_FIELDS
        }
        return {
            "event_name": self.name_for(type(event)),
            "event_id": str(event.event_id),
            "occurred_on": event.occurred_on.isoformat(),
            "correlation_id": event.correlation_id,
            "payload": payload,
        }

    def encode_json(self, event: DomainEvent, **dumps_kwargs: Any) -> str:
        """Encode an event and serialize the envelope as JSON."""
        return json.dumps(self.encode(event), **dumps_kwargs)

    def _encode_value(self, value: Any) -> Any:
        encoder = self._encoders.get(type(value))
        if encoder is not None:
            return encoder(value)
        if value is None or isinstance(value, (str, bool, int, float)):
            return value
        if isinstance(value, (Decimal, UUID, DomainId)):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Enum):
            return self._encode_value(value.value)
        if isinstance(value, Mapping):
            return {str(k): self._encode_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self._encode_value(item) for item in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {
                field.name: self._encode_value(getattr(value, field.name))
                for field in dataclasses.fields(value)
            }
        raise SerializationError(
            f"cannot encode {type(value).__name__}; "
            f"register a codec with registry.register_codec({type(value).__name__}, …)"
        )

    # --- decoding -----------------------------------------------------------

    def decode(self, envelope: Mapping[str, Any]) -> DomainEvent:
        """Rebuild the event an envelope describes.

        Unknown payload keys are ignored, so a consumer keeps working when a
        producer adds a field.
        """
        try:
            name = envelope["event_name"]
        except KeyError:
            raise SerializationError("envelope has no 'event_name'") from None

        event_type = self.type_for(name)
        payload = envelope.get("payload") or {}
        hints = _type_hints(event_type)

        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(event_type):
            if not field.init or field.name in _ENVELOPE_FIELDS:
                continue
            if field.name not in payload:
                continue  # let the dataclass apply its default, or complain
            kwargs[field.name] = self._decode_value(
                payload[field.name], hints.get(field.name), field.name, name
            )

        if (raw_id := envelope.get("event_id")) is not None:
            kwargs["event_id"] = UUID(str(raw_id))
        if (raw_on := envelope.get("occurred_on")) is not None:
            kwargs["occurred_on"] = datetime.fromisoformat(str(raw_on))
        kwargs["correlation_id"] = envelope.get("correlation_id")

        try:
            return event_type(**kwargs)
        except TypeError as exc:
            raise SerializationError(f"cannot rebuild {name}: {exc}") from exc

    def decode_json(self, raw: str | bytes, **loads_kwargs: Any) -> DomainEvent:
        """Parse a JSON envelope and rebuild the event."""
        try:
            envelope = json.loads(raw, **loads_kwargs)
        except json.JSONDecodeError as exc:
            raise SerializationError(f"envelope is not valid JSON: {exc}") from exc
        if not isinstance(envelope, Mapping):
            raise SerializationError("envelope must be a JSON object")
        return self.decode(envelope)

    def _decode_value(
        self, value: Any, annotation: Any, field_name: str, event_name: str
    ) -> Any:
        try:
            return self._decode(value, annotation)
        except SerializationError:
            raise
        except (TypeError, ValueError) as exc:
            raise SerializationError(
                f"cannot decode {event_name}.{field_name}: {exc}"
            ) from exc

    def _decode(self, value: Any, annotation: Any) -> Any:
        if annotation is None or annotation is Any or value is None:
            return value

        decoder = self._decoders.get(annotation)
        if decoder is not None:
            return decoder(value)

        origin = get_origin(annotation)
        if origin in (Union, UnionType):
            return self._decode(value, _single_type(get_args(annotation)))
        if origin in _SEQUENCES:
            (item_type, *_) = get_args(annotation) or (Any,)
            return _SEQUENCES[origin](self._decode(item, item_type) for item in value)
        if origin is dict:
            args = get_args(annotation)
            value_type = args[1] if len(args) == 2 else Any
            return {k: self._decode(v, value_type) for k, v in value.items()}
        if origin is not None:  # some other generic — hand the raw value over
            return value

        if annotation is DomainId:
            return _domain_id(value)
        if annotation is Decimal:
            return Decimal(str(value))
        if annotation is UUID:
            return UUID(str(value))
        if annotation is datetime:
            return datetime.fromisoformat(str(value))
        if annotation is date:
            return date.fromisoformat(str(value))
        if isinstance(annotation, type):
            if issubclass(annotation, Enum):
                return annotation(value)
            if dataclasses.is_dataclass(annotation):
                return self._decode_dataclass(value, annotation)
        return value

    def _decode_dataclass(self, value: Any, target: type) -> Any:
        if not isinstance(value, Mapping):
            raise SerializationError(
                f"expected an object for {target.__name__}, got {type(value).__name__}"
            )
        hints = _type_hints(target)
        kwargs = {
            field.name: self._decode(value[field.name], hints.get(field.name))
            for field in dataclasses.fields(target)  # ty: ignore[invalid-argument-type]
            if field.init and field.name in value
        }
        return target(**kwargs)


def _single_type(args: tuple[Any, ...]) -> Any:
    """The one meaningful member of a union (``X | None`` is the common case)."""
    concrete = [arg for arg in args if arg is not type(None)]
    if len(concrete) != 1:
        # An ambiguous union can't drive reconstruction; pass the value through.
        return Any
    return concrete[0]


def _domain_id(value: Any) -> DomainId:
    """Rebuild a DomainId, preferring UUID — the DomainIdType convention."""
    if isinstance(value, DomainId):
        return value
    try:
        return DomainId(UUID(str(value)))
    except ValueError:
        return DomainId(str(value))


def _type_hints(target: type) -> dict[str, Any]:
    """Resolved annotations, tolerant of a forward reference we can't see."""
    try:
        return get_type_hints(target)
    except Exception:  # any resolution failure is handled below
        pass
    # One unresolvable annotation shouldn't cost us every other field: walk the
    # hierarchy and keep whatever each class can resolve on its own.
    hints: dict[str, Any] = {}
    for klass in reversed(target.__mro__):
        try:
            hints.update(get_type_hints(klass))
        except Exception:  # that class's fields stay raw
            continue
    return hints
