# Migrations Internals

This page covers the underlying machinery. You generally interact with it only when building tooling on top of norm, writing custom diff logic, or running migrations programmatically.

---

## SchemaState

`SchemaState` is an in-memory representation of a Postgres schema. It is the common currency between the diff engine, the snapshot builder, and the replay system.

```python
>>> from norm.migrations.state import (
...     SchemaState, TableState, ColumnState,
...     UniqueConstraint, ForeignKeyConstraint, IndexDef, ViewState,
... )
>>> state = SchemaState(
...     tables={
...         "users": TableState(
...             columns={
...                 "id":    ColumnState(type="INTEGER", nullable=False, primary_key=True, has_sequence_default=True),
...                 "email": ColumnState(type="TEXT", nullable=False),
...             },
...             constraints=[
...                 UniqueConstraint(name="uq_users_email", columns=("email",)),
...             ],
...             indexes=[
...                 IndexDef(name="idx_users_email", columns=("email",), unique=True),
...             ],
...             schema="public",
...         ),
...     },
...     extensions={"uuid-ossp"},
...     schemas={"public"},
... )
>>> "users" in state.tables
True
>>> state.tables["users"].columns["id"].primary_key
True
>>> state.tables["users"].columns["id"].has_sequence_default
True

```

### ColumnState

| Field | Type | Notes |
|-------|------|-------|
| `type` | `str` | SQL type; `SERIAL`/`BIGSERIAL` are normalised to `INTEGER`/`BIGINT` |
| `nullable` | `bool` | Default `True` |
| `default` | `str \| None` | SQL default expression |
| `primary_key` | `bool` | |
| `has_sequence_default` | `bool` | `True` when original type was `SERIAL`/`BIGSERIAL` |

`ColumnDef` is an alias for `ColumnState` (kept for backward compatibility in migration files on disk).

```python
>>> from norm.migrations.operations import ColumnDef
>>> ColumnDef is ColumnState
True

```

### Constraint types

```python
>>> UniqueConstraint(name="uq_foo", columns=("col_a", "col_b"))
UniqueConstraint(name='uq_foo', columns=('col_a', 'col_b'), type='unique')

>>> ForeignKeyConstraint(
...     name="fk_bar",
...     columns=("user_id",),
...     references_schema="public",
...     references_table="users",
...     references_column="id",
...     on_delete="CASCADE",
...     on_update=None,
... )
ForeignKeyConstraint(name='fk_bar', columns=('user_id',), references_schema='public', references_table='users', references_column='id', on_delete='CASCADE', on_update=None, type='foreign_key')

```

---

## SchemaPipeline

`SchemaPipeline` computes the forward and reverse operation lists needed to evolve the current schema to the target schema.

```python
>>> from norm.migrations.pipeline import SchemaPipeline

```

### Class methods

```python
>>> empty = SchemaState(tables={}, extensions=set(), schemas=set())
>>> pipeline = SchemaPipeline.from_states(empty, empty)
>>> pipeline.has_changes
False
>>> pipeline.forward
[]
>>> pipeline.reverse
[]

```

```python
>>> pipeline = SchemaPipeline.build(migration_files=[], models=[])
>>> pipeline.has_changes
False

```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `current` | `SchemaState` | State derived from replaying migration files |
| `target` | `SchemaState` | State derived from introspecting Table definitions |
| `forward` | `list[Operation]` | Ops to apply (current → target) |
| `reverse` | `list[Operation]` | Ops to undo (target → current) |
| `has_changes` | `bool` | `True` if `forward` is non-empty |

---

## diff_states

```python
>>> from norm.migrations.draft import diff_states
>>> forward, reverse = diff_states(
...     SchemaState(tables={}, extensions=set(), schemas=set()),
...     SchemaState(tables={}, extensions=set(), schemas=set()),
... )
>>> forward
[]
>>> reverse
[]

```

The diff engine compares two `SchemaState` objects and emits the minimum set of operations to transform `current` into `target`. Order matters: schemas and extensions are created first, tables are created/altered, then constraints/indexes follow.

---

## models_to_schema_state (snapshot)

Introspects `Table` / `View` class definitions and produces a `SchemaState`:

```python
>>> from norm.migrations.snapshot import models_to_schema_state
>>> from norm import Table, Field, PrimaryKey, Unique, field, TableMeta, db
>>> class UserM(Table):
...     __meta__ = TableMeta(schema="public")
...     id:    PrimaryKey[int] = field(default=db.serial())
...     email: Unique[str]
...
>>> state = models_to_schema_state([UserM])
>>> "user_ms" in state.tables
True
>>> state.tables["user_ms"].columns["id"].has_sequence_default
True

```

This is the "target" side of the diff. It reads `__fields__`, `__meta__`, and `FieldDef` metadata to produce `ColumnState`, `UniqueConstraint`, `ForeignKeyConstraint`, and `IndexDef` entries.

Python-to-SQL type mapping (partial):

| Python type | SQL type |
|-------------|----------|
| `int` (pk, db_default) | `SERIAL` |
| `int` | `INTEGER` |
| `str` | `TEXT` |
| `float` | `DOUBLE PRECISION` |
| `bool` | `BOOLEAN` |
| `datetime` | `TIMESTAMPTZ` |
| `date` | `DATE` |
| `uuid.UUID` | `UUID` |
| `dict` / `list` | `JSONB` |

---

## replay_migrations (replay)

Builds a `SchemaState` by loading and replaying a list of migration files:

```python
>>> from norm.migrations.replay import replay_migrations
>>> state = replay_migrations([])
>>> state.tables
{}

```

Each operation's `.apply(state)` is called in order. The result represents the schema as it would look after all those migrations have been applied.

---

## MigrationRunner

Manages applying and rolling back migrations against a live database.

```python
>>> import asyncpg  # doctest: +SKIP
>>> from norm import AsyncConnection  # doctest: +SKIP
>>> from norm.migrations.runner import MigrationRunner  # doctest: +SKIP
>>> raw = await asyncpg.connect("postgresql://localhost/mydb")  # doctest: +SKIP
>>> conn = AsyncConnection(raw)  # doctest: +SKIP
>>> runner = MigrationRunner(conn, migrations_dir="migrations")  # doctest: +SKIP
>>> applied = await runner.applied()  # doctest: +SKIP
>>> pending = await runner.pending()  # doctest: +SKIP
>>> newly_applied = await runner.apply()  # doctest: +SKIP
>>> await runner.rollback("0002_add_posts")  # doctest: +SKIP
>>> await runner.rollback("0001_create_users", force=True)  # doctest: +SKIP

```

The runner creates and maintains the `norm_migrations` tracking table automatically.

---

## Codegen

Generate a migration file from a list of forward and reverse operations:

```python
>>> from norm.migrations.codegen import make_migration  # doctest: +SKIP
>>> from pathlib import Path  # doctest: +SKIP
>>> path = make_migration(  # doctest: +SKIP
...     migrations_dir=Path("migrations"),
...     number=3,
...     forward=pipeline.forward,
...     reverse=pipeline.reverse,
...     dependencies=["0002_add_posts"],
...     label="add_comments",
... )

```

---

## Lint checks

```python
>>> from norm.migrations.lint import check_atomic_mismatch, check_run_sql_ddl  # doctest: +SKIP
>>> from norm.migrations.config import load_config  # doctest: +SKIP
>>> from pathlib import Path  # doctest: +SKIP
>>> cfg = load_config(Path("."))  # doctest: +SKIP
>>> issues = check_atomic_mismatch(cfg)  # doctest: +SKIP
>>> issues = check_run_sql_ddl(cfg)  # doctest: +SKIP

```

---

## Model discovery

```python
>>> from norm.migrations.discovery import (
...     import_models_module,
...     models_for,
...     existing_migration_files,
...     next_number,
... )
>>> from norm.migrations.config import NormConfig
>>> from pathlib import Path
>>> cfg = NormConfig(migrations_dir=Path("migrations"), models="myapp.models")
>>> existing_migration_files(Path("migrations"))
[]
>>> next_number(Path("migrations"))
1

```
