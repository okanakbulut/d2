# d2

A type-safe query builder for Python. Define your schema as classes and build SELECT/INSERT/UPDATE/DELETE queries that your type checker understands — column references, filters, and results are all statically typed.

- **Type-safe query builder** — immutable, chainable builders where columns and results are typed end to end
- **Declarative schema** — define tables and views as Python classes with type annotations
- **Integrated migrations** — schema diffing, codegen, apply/rollback, lint checks
- **Async execution** — runs on [asyncpg](https://github.com/MagicStack/asyncpg) today, with results deserialised via [msgspec](https://github.com/jcrist/msgspec)

Currently targets PostgreSQL via asyncpg; the builder is dialect-agnostic by design, with support for more databases and drivers planned.

**Documentation:** <https://okanakbulut.github.io/d2/>

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

## License

[MIT](LICENSE)
