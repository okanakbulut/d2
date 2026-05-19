# Getting Started

## Installation

```bash
pip install norm
# Runtime dependencies: asyncpg, pypika, msgspec
```

## Configuration

Norm reads project settings from `pyproject.toml`:

```toml
[tool.norm]
migrations_dir = "migrations"   # where .py migration files live
models = "myapp.models"         # dotted import path to your Table definitions
```

Both keys have defaults (`./migrations` and `./models`) so the section is optional for simple layouts.

## Defining your first table

```python
>>> from norm import Table, Field, PrimaryKey, Unique, field, TableMeta
>>> from norm.model import ForeignKey
>>> class User(Table):
...     id:       PrimaryKey[int] = field(db_default=True)
...     username: Unique[str]
...     email:    Unique[str]
...     bio:      Field[str | None]
...
>>> class Post(Table):
...     id:      PrimaryKey[int] = field(db_default=True)
...     user_id: Field[int] = field(fk=ForeignKey(to=User.id, on_delete="CASCADE"))
...     title:   Field[str]
...     body:    Field[str | None]
...

```

Key points:
- Subclass `Table` for read-write tables, `View` for read-only.
- Use `PrimaryKey[T]`, `Unique[T]`, `Field[T]` annotations to declare columns.
- `field(db_default=True)` marks columns the database fills in (SERIAL, DEFAULT, etc.) — norm skips them in INSERT by default.
- `Field[str | None]` marks a column as nullable.
- `TableMeta` sets schema, table name overrides, composite indexes, and extensions.

## Building a query (no DB required)

```python
>>> sql, params = (
...     User
...     .select(User.id, User.username)
...     .where(User.id > 0)
...     .build()
... )
>>> sql
'SELECT "user"."id","user"."username" FROM "public"."user" WHERE "user"."id">$1'
>>> params
(0,)

```

## Connecting and running a query

```python
>>> import asyncpg  # doctest: +SKIP
>>> from norm import AsyncConnection  # doctest: +SKIP
>>> import msgspec  # doctest: +SKIP
>>> class UserRow(msgspec.Struct):  # doctest: +SKIP
...     id: int
...     username: str
...
>>> raw_conn = await asyncpg.connect("postgresql://localhost/mydb")  # doctest: +SKIP
>>> conn = AsyncConnection(raw_conn)  # doctest: +SKIP
>>> rows = await conn.fetch(  # doctest: +SKIP
...     User.select(User.id, User.username).where(User.id > 0),
...     list[UserRow],
... )
>>> row = await conn.fetch(  # doctest: +SKIP
...     User.select(User.id, User.username).where(User.id == 1),
...     UserRow,
... )
>>> await conn.execute(  # doctest: +SKIP
...     User.insert(username="alice", email="alice@example.com")
... )
>>> await raw_conn.close()  # doctest: +SKIP

```

## Generating and applying migrations

After defining your tables, generate the first migration:

```bash
python -m norm.migrations make --label initial
```

This creates `migrations/0001_initial.py`. Apply it:

```bash
python -m norm.migrations apply --dsn postgresql://localhost/mydb
```

See [Migrations](migrations.md) for the full workflow.
