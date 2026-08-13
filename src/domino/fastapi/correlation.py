"""Per-request correlation id as a pure-ASGI middleware.

Reads an incoming correlation-id header (default ``X-Request-ID``), opens a
:func:`~domino.core.correlation.correlation_scope` for the whole request, and
echoes the id back on the response. Because a use case *reuses* an active scope,
every log line and domain event produced while handling the request shares this
id automatically.

It is written as a **pure ASGI** middleware on purpose: Starlette runs the
endpoint in the same context as the middleware, so the contextvar set here is
visible downstream. A ``BaseHTTPMiddleware`` would run the endpoint in a separate
task, and the contextvar would not propagate.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders

from domino.core.correlation import correlation_scope

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class CorrelationIdMiddleware:
    """ASGI middleware binding a correlation id to each HTTP request."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name
        self._lookup = header_name.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming: str | None = None
        for key, value in scope["headers"]:
            if key == self._lookup:
                incoming = value.decode("latin-1")
                break

        with correlation_scope(incoming) as cid:

            async def send_with_header(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers[self.header_name] = cid
                await send(message)

            await self.app(scope, receive, send_with_header)
