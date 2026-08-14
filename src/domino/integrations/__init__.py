"""Optional integrations with third-party frameworks.

Each subpackage is an optional extra and pulls in its own dependency; Domino's
core stays dependency-free. Nothing here is imported eagerly — reach for a
specific integration by its full path so importing ``domino`` never requires the
framework:

- :mod:`domino.integrations.sqlalchemy` — infrastructure layer (``domino[sqlalchemy]``);
- :mod:`domino.integrations.fastapi` — presentation layer (``domino[fastapi]``).
"""
