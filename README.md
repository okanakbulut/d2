# d2

Async-first PostgreSQL ORM for Python with a composable query builder and integrated migrations.

- **Declarative schema** — define tables and views as Python classes with type annotations
- **Composable query builder** — immutable, chainable SELECT/INSERT/UPDATE/DELETE builders
- **Integrated migrations** — schema diffing, codegen, apply/rollback, lint checks
- **Async-first** — built on [asyncpg](https://github.com/MagicStack/asyncpg); results deserialised via [msgspec](https://github.com/jcrist/msgspec)

**Documentation:** <https://okanakbulut.github.io/d2/> (source in [docs/](docs/) — every example is a doctest, verified in CI)

## Installation

Requires Python 3.14+ and PostgreSQL.

```sh
pip install d2
```

## Quick example

```python
from d2 import Table, Field, PrimaryKey, Unique, field, db

class User(Table):
    id:    PrimaryKey[int] = field(default=db.serial())
    name:  Field[str]
    email: Unique[str]

q = (
    User
    .select(User.id, User.name)
    .where(User.email.ilike("%@example.com"))
    .order_by(User.id)
    .limit(10)
)

q.build()
# ('SELECT "users"."id","users"."name" FROM "public"."users"
#   WHERE "users"."email" ILIKE $1 ORDER BY "users"."id" ASC LIMIT 10',
#  ('%@example.com',))
```

See [Getting Started](docs/getting-started.md) for configuration, connections, and running your first migration.

## Development

The project is managed with [uv](https://docs.astral.sh/uv/):

```sh
uv sync                          # install dependencies
uv run pytest -m 'not integration'   # unit tests + doc doctests (no database needed)

docker compose up -d             # start PostgreSQL 17 for integration tests
uv run pytest                    # full suite
```

The documentation site lives in [website/](website/) (Astro + Starlight) and renders the markdown in [docs/](docs/) directly:

```sh
cd website
npm install
npm run dev
```

## License

[MIT](LICENSE)
