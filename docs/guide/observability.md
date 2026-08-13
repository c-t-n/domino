# Correlation ids & logging

Two things you'll want in any real application — a way to trace one operation across
logs and events, and contextual logging — Domino gives you with **zero plumbing**.

## Correlation ids

A **correlation id** ties together everything that happens while handling one
request or message. Domino keeps it in a `contextvars` context, so it flows through
the call stack (and across `await`) on its own. Application code and aggregates
never pass it around.

Every `UseCase.execute` call automatically opens a correlation scope, and every
`DomainEvent` created inside it captures the id:

```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        order = Order.place(command.customer_id)
        order.confirm()  # the OrderConfirmed event captures the current id
        ...


# order.pull_pending_events()[0].correlation_id  ->  "8f3e5c…"
```

- **One id per top-level call.** Each `execute` gets a fresh id.
- **Nested use cases share it.** If one use case calls another, they use the same
  id, so the whole causal chain is traceable.
- **Upstream ids are continued.** If the command carries a `correlation_id`, that
  trace is continued instead of a new one being started — handy for propagating a
  header from an upstream service.

Read the current id anywhere with `get_correlation_id()`. At boundaries Domino
doesn't own — web middleware, a message consumer, a background job — open a scope
yourself:

```python
from domino import correlation_scope

with correlation_scope(incoming_id):  # or no argument to generate one
    handle(message)
```

## Contextual logging: `self.log`

Use cases, event handlers and aggregate roots expose `self.log`, a logger that
stamps every line with the **class doing the logging** and the **current
correlation id** — automatically.

```python
class PlaceOrder(UseCase[PlaceOrderCommand, DomainId]):
    def execute(self, command: PlaceOrderCommand) -> DomainId:
        self.log.info("placing order for %s", command.customer_id)
        ...
```

```
INFO domino [PlaceOrder] [cid=8f3e5c…] placing order for 1f7f8c…
```

The class name and id are also attached to the record as `domino_context` and
`correlation_id` fields, ready for structured/JSON handlers.

### It composes

Because both features are ambient, a single operation shows one coherent trace. In
the [order tutorial](../tutorial/order-domain.md) the two `OrderConfirmed` handlers
log the **same** id (same use-case call) while a later `OrderShipped` handler shows
a **different** one (a separate call) — with no code passing anything.

### Domino doesn't configure logging

Libraries shouldn't hijack your logging config, so Domino only logs to the `domino`
logger and leaves setup to you:

```python
import logging

logging.basicConfig(level=logging.INFO)  # turn it on in your app
logging.getLogger("domino").setLevel("INFO")  # tune the domino logger
```

Want the same `self.log` on your own classes (a domain service, a repository)? Mix
in `LoggerMixin`, or call `get_logger("MyThing")` directly.

---

Next: [Configuration →](configuration.md)
