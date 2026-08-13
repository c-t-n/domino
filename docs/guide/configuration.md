# Configuration

Domino works out of the box, but a few cross-cutting behaviours can be tuned in
**one place**. Call `configure()` once, at application startup; only the arguments
you pass change, everything else keeps its default.

```python
from uuid import uuid4
from domino import configure

# 16-char correlation ids instead of a 32-char uuid hex
configure(correlation_id_factory=lambda: uuid4().hex[:16])
```

## What you can configure

| Setting | Feeds | Default |
| --- | --- | --- |
| `correlation_id_factory` | `new_correlation_id()`, every correlation scope, and `event.correlation_id` | `uuid4().hex` |
| `id_factory` | `DomainId.generate()` | `uuid4()` |

### Example: NanoID everywhere

```python
from nanoid import generate
from domino import configure

configure(
    correlation_id_factory=lambda: generate(size=16),
    id_factory=generate,  # used by DomainId.generate()
)
```

## Reading and resetting

```python
from domino import get_config, reset_config

get_config().correlation_id_factory()  # the current factory
reset_config()  # restore defaults — handy in tests
```

!!! note "Strategy is global, value is per-operation"
    The configuration is process-wide — it sets the *strategy* for generating ids.
    The correlation id *value* is still per-operation, carried by a contextvar (see
    [correlation ids](observability.md)). Set configuration once at startup, not
    per request.

!!! tip "Isolate config in tests"
    Because configuration is global, a test that calls `configure()` should reset
    it afterwards so it doesn't leak into other tests:

    ```python
    import pytest
    from domino import reset_config


    @pytest.fixture(autouse=True)
    def _reset_domino_config():
        reset_config()
        yield
        reset_config()
    ```

---

See it all together in the [Order domain tutorial →](../tutorial/order-domain.md)
