# Norm Developer Guide

Norm is a Python ORM for PostgreSQL. It provides:

- **Declarative schema** — define tables and views as Python classes with type annotations
- **Composable query builder** — immutable, chainable SELECT/INSERT/UPDATE/DELETE builders
- **Integrated migrations** — schema diffing, codegen, apply/rollback, lint checks
- **Async-first** — built on `asyncpg`; results deserialised via `msgspec`

## Pages

| Page | What it covers |
|------|---------------|
| [Getting Started](getting-started.md) | Installation, config, first table and query |
| [Schema](schema.md) | `Table`, `View`, field types, `TableMeta`, `ForeignKey`, `IndexDef` |
| [Querying](querying.md) | SELECT, filters, joins, ordering, pagination, group by, set operations |
| [Writes](writes.md) | INSERT, UPDATE, DELETE, upsert, `returning`, `excluded()` |
| [Advanced Queries](advanced-queries.md) | CTEs, JSON output, `prefetch`, window functions, scalar subqueries |
| [Connection](connection.md) | `AsyncConnection`, `fetch` / `execute` / `fetchval`, transactions |
| [Migrations](migrations.md) | CLI workflow, `Migration` class, all 22 operations |
| [Migrations Internals](migrations-internals.md) | `SchemaState`, `SchemaPipeline`, `MigrationRunner`, codegen, lint |
| [Configuration](configuration.md) | `pyproject.toml`, `NormConfig`, model discovery |

## Quick example

```python
>>> from norm import Table, Field, PrimaryKey, Unique, field, TableMeta, db
>>> class User(Table):
...     id:    PrimaryKey[int] = field(default=db.serial())
...     name:  Field[str]
...     email: Unique[str]
...
>>> q = (
...     User
...     .select(User.id, User.name)
...     .where(User.email.ilike("%@example.com"))
...     .order_by(User.id)
...     .limit(10)
... )
>>> q.build()
('SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."email" ILIKE $1 ORDER BY "users"."id" ASC LIMIT 10', ('%@example.com',))

```
