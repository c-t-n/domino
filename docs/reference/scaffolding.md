# Scaffolding a bounded context

Domino ships a small script that generates a [layered](../ddd/layering.md) bounded
context — the domain / application / infrastructure folders with correct,
decorator-free starter stubs (an aggregate, an event, a command, a use case and an
in-memory repository). It's a fast way to start a new context with the conventions
already in place.

The script lives with the Domino agent skill at
`skills/domino/scripts/scaffold.py` in the repository.

## Usage

```bash
python scaffold.py <context_name> [--path DIR] [--aggregate NAME]
```

Examples:

```bash
python scaffold.py billing
python scaffold.py catalog --path src --aggregate Product
```

Existing files are never overwritten — only missing ones are created — so it's safe
to re-run.

## What it generates

For `python scaffold.py inventory --aggregate StockItem`:

```
inventory/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── value_objects.py     # a sample ValueObject
│   ├── events.py            # StockItemCreated(DomainEvent)
│   └── aggregates.py        # StockItem(AggregateRoot) with a create() factory
├── application/
│   ├── __init__.py
│   ├── commands.py          # CreateStockItemCommand(Command)
│   └── use_cases.py         # CreateStockItem(UseCase[...]) wired to the repo + UoW
└── infrastructure/
    ├── __init__.py
    └── repositories.py      # in-memory StockItemRepository(Repository[StockItem])
```

Every generated class follows the conventions in this documentation: no stray
`@dataclass`, an `_id` field with `default_factory=DomainId.generate`, events with
inherited fields left alone, and a use case that saves through a `UnitOfWork`. Flesh
out the behaviour, then wire the use case with an `EventBus` where you compose your
application.

## Next steps after scaffolding

1. Add real fields and behaviour to the aggregate — put the rules *inside* it.
2. Replace the in-memory repository with a real store when you need one (the
   interface stays the same).
3. Register handlers on an `EventBus` and publish the aggregate's events after
   commit.
