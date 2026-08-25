# FastAPI

The optional `domino.integrations.fastapi` subpackage wires the **presentation layer** — the
HTTP entry point — to your application and domain, without leaking framework
concerns inward. It is async-first: you hand it the unit of work your app runs
on — typically the [async SQLAlchemy](../infrastructure/sqlalchemy.md#async) one,
but any `UnitOfWork` / `AsyncUnitOfWork` will do.

```bash
uv add "domino[fastapi]" "domino[sqlalchemy]" aiosqlite
# or: pip install "domino[fastapi]" "domino[sqlalchemy]" aiosqlite
```

## What it gives you

One call, `install_domino`, wires four things onto a FastAPI app:

| Piece | What it does |
|-------|--------------|
| **Unit-of-work dependency** | a fresh unit of work **per request**, injectable into any route |
| **Correlation middleware** | one correlation id per request, on every log line and event |
| **Domain-error handlers** | `DomainError` → HTTP status + a consistent JSON body |
| **Event dispatch** | the unit of work publishes the events queued during the scope, after commit |

Plus a helper to turn query parameters into
[specifications](../guide/specifications.md) for `list` endpoints.

## Wiring the app

Create the engine and the session factory yourself (dispose the engine in the
app's `lifespan` on shutdown) and load Domino's
[configuration](../guide/configuration.md) at startup. Then call `install_domino`
at construction — **before** the app starts, because it adds middleware — passing
a **factory** that builds the unit of work each request should get.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from domino import configure
from domino.events import EventBus
from domino.integrations.fastapi import install_domino
from domino.integrations.sqlalchemy import AsyncSqlAlchemyUnitOfWork

configure(correlation_id_factory=lambda: uuid4().hex[:16])  # optional

engine = create_async_engine("postgresql+asyncpg://…")
session_factory = async_sessionmaker(engine, expire_on_commit=False)

bus = EventBus()
bus.register(OrderConfirmed, AnnounceConfirmation())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
install_domino(
    app,
    unit_of_work=lambda: AsyncSqlAlchemyUnitOfWork(
        session_factory=session_factory,
        repositories={"orders": OrderRepository},
        event_bus=bus,  # omit to skip event dispatch
    ),
)
```

The factory is the only persistence argument: repositories, the event bus and the
session factory are configured on the unit of work it returns, not on
`install_domino`. Anything implementing `UnitOfWork` / `AsyncUnitOfWork` fits, so
an in-memory one is enough for tests.

!!! note "A factory, not an instance"
    A unit of work holds per-scope state — a session, the repositories bound to
    it, the event queue — so one instance cannot serve two requests at once.
    `install_domino` therefore takes a zero-arg callable and raises `TypeError`
    if you hand it an instance. Long-lived objects (the engine, the
    `async_sessionmaker`, the bus) are built once and captured by the closure;
    only the unit of work itself is rebuilt per request.

`install_domino` accepts flags to opt out (`correlation=False`,
`exception_handlers=False`) and to tune the correlation header
(`correlation_header=...`) or the status map (`status_map=...`).

## The per-request unit of work

`UnitOfWorkDep` calls your factory once per request, so each request gets its own
unit of work. It is handed over **un-entered** — opening the transaction scope is
the caller's job, either in the route or inside the
[use case](../guide/use-cases.md#async-use-cases). Each `async with` block opens a
fresh session and commits (or rolls back) on exit:

```python
from domino.integrations.fastapi import UnitOfWorkDep


@app.post("/orders", status_code=201)
async def place_order(body: PlaceOrderBody, uow: UnitOfWorkDep) -> dict[str, str]:
    async with uow:
        order_id = await PlaceOrder(uow).execute(
            PlaceOrderCommand(customer_id=DomainId(body.customer_id))
        )
    return {"id": str(order_id)}
```

The route stays thin: it opens the transaction, maps the request body to a
`Command`, calls the use case, and shapes the response. All the rules live in the
domain.

To swap the unit of work in a test, override the dependency the usual FastAPI
way:

```python
app.dependency_overrides[get_unit_of_work] = lambda: UnitOfWork({"orders": fake})
```

## Correlation ids

The middleware reads an incoming correlation-id header (default `X-Request-ID`),
opens a [correlation scope](../guide/observability.md) for the whole request, and
echoes the id on the response. Because a use case *reuses* an active scope, every
log line and every domain event raised while handling the request shares that id —
with nothing to thread through your code.

!!! note "Why a pure-ASGI middleware"
    It is written as pure ASGI, not `BaseHTTPMiddleware`, on purpose: Starlette
    runs the endpoint in the same context, so the correlation contextvar set by the
    middleware is visible to the endpoint and the use case. A `BaseHTTPMiddleware`
    runs the endpoint in a separate task and the contextvar would not propagate.

## Domain errors → HTTP

Raise domain errors anywhere; the installed handlers map them to status codes and
a consistent JSON body — `{"code", "message", "correlation_id"}`:

| Exception | Status |
|-----------|--------|
| `DomainNotFoundError` | 404 |
| `DomainValidationError` | 422 |
| `DomainStateError` | 409 |
| `DomainError` (any other) | 400 |

Resolution walks the class hierarchy, so a custom `DomainError` subclass falls
back to its nearest mapped ancestor. Override or extend the mapping with
`status_map=` on `install_domino` (or call `install_exception_handlers` directly).

```json
// 409 on confirming an already-confirmed order
{ "code": "STATE_ERROR", "message": "order is already confirmed",
  "correlation_id": "dfb2046730dd4c46" }
```

## Domain events after commit

When you pass an `event_bus` to the unit of work, the events a use case queued
with `uow.enqueue_events(...)` are published **after the transaction commits**
(see [the SQLAlchemy async notes](../infrastructure/sqlalchemy.md#async)).
Handlers run once the data is durable, so a route needn't touch the bus —
confirming an order persists it *and* fans out `OrderConfirmed` to its handlers,
all within the request's correlation scope.

## Filtering from query parameters

For `list` endpoints backed by
[`AsyncFilterable`](../infrastructure/sqlalchemy.md#async), `query_filter` turns
whitelisted query parameters into specifications. The operator is an optional
`__op` suffix (`eq` when omitted); the field map both whitelists and converts:

```python
from typing import Annotated
from fastapi import Depends
from domino.integrations.fastapi import query_filter

OrderFilters = Annotated[list, Depends(query_filter({"status": str, "priority": int}))]


@app.get("/orders")
async def list_orders(uow: UnitOfWorkDep, specs: OrderFilters) -> list[dict]:
    async with uow:
        orders = await uow.orders.list(*specs)
        return [{"id": str(o.id), "status": o.status} for o in orders]
```

`?status=confirmed&priority__ge=5` becomes `eq("status", "confirmed")` AND
`ge("priority", 5)`. Anything outside the whitelist (`limit`, `offset`, `sort`, …)
is ignored; a whitelisted field with an unknown operator raises
`DomainValidationError` — a 422 through the handlers above.

## A full runnable example

See `examples/order_fastapi.py` in the repository — the order domain exposed over
HTTP, with an in-process demo you can run directly (`python
examples/order_fastapi.py`) or serve with `uvicorn examples.order_fastapi:app`.
