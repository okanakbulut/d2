---
title: d2 Developer Guide
description: "A Python ORM built around a type-safe query builder — declarative schemas, statically-typed queries, integrated migrations."
---

d2 is a Python ORM built around a powerful, type-safe query builder. You define your schema as classes and build queries that your type checker understands — column references, filters, and results are all statically typed. It provides:

- **Type-safe query builder** — immutable, chainable SELECT/INSERT/UPDATE/DELETE builders where columns and results are typed end to end
- **Declarative schema** — define tables and views as Python classes with type annotations
- **Integrated migrations** — schema diffing, codegen, apply/rollback, lint checks
- **Async execution** — runs on `asyncpg` today; results deserialised via `msgspec`

d2 currently targets PostgreSQL, but the query builder is dialect-agnostic by design, with support for more databases and drivers planned.

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
| [Configuration](configuration.md) | `pyproject.toml`, `D2Config`, model discovery |

## Quick example

```python
>>> from d2 import Table, Field, PrimaryKey, Unique, field, TableMeta, db
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
