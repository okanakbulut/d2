# 14 — Django-style Migration System

Status: broken down — see child issues 140-148
Type: design doc

## Implementation slices

This issue is the design doc. Implementation is split into nine vertical-slice issues:

- [140 — Tracer: hand-written CreateTable migration through `apply`](140-tracer-create-table-migration.md)
- [141 — Model snapshot + diff + codegen + CLI for tables](141-snapshot-diff-codegen-cli-for-tables.md)
- [142 — Column ops: Add/Drop/Rename + granular column modifications](142-column-ops-add-drop-rename-and-granular-modify.md)
- [143 — Constraints + indexes with `concurrent=True` default](143-constraints-and-indexes-concurrent-defaults.md)
- [144 — Foreign keys](144-foreign-keys.md)
- [145 — `View(query=...)` declaration + view ops + view diff](145-views-query-kwarg-and-diff.md)
- [146 — Extensions + schemas](146-extensions-and-schemas.md)
- [147 — Reverse operations codegen + rollback](147-reverse-operations-and-rollback.md)
- [148 — Escape hatches: `RunSQL` / `RunPython` + `check` DDL lint](148-escape-hatches-run-sql-and-run-python.md)

Dependency graph: 01 → 140 → 141 → {142, 145, 146}; 142 → 143 → 144; {142, 143, 144, 145, 146} → 147; 140 → 148.

## What to build

A Django-style migration system for norm with four capabilities:

1. **Schema metadata on models** — declare columns, foreign keys, indexes, and extensions on `Table` and `View` subclasses.
2. **DDL operation data classes** — each DDL action is a dataclass with `apply(state)` (mutates an in-memory `SchemaState`) and `to_ddl()` (renders the SQL string), kept intentionally separate.
3. **Migration files** — numbered Python files (`0001_initial.py`) each with a `Migration` subclass carrying both `operations` (forward) and `reverse_operations` (backward) lists. Raw SQL and Python callables are valid for data-only escape hatches; schema changes must use DDL ops.
4. **Three commands** — `make`, `apply`, `check`.

### Constraint: only declared models, never runtime clones

`NormMeta.__new__` creates throwaway class objects whenever `.clone()`, `.aliased()`, or set-op methods are called. These must never be picked up for migration purposes.

The mechanism is simple: every `clone()` / `aliased()` / `_make_set_op()` path includes `"__table__"` in the namespace it passes to `NormMeta(...)`. So:

- `NormMeta.__new__` registers a model into `_MODEL_REGISTRY: dict[str, type]` (keyed by `f"{cls.__module__}.{cls.__qualname__}"`) **only** when `"__table__" not in namespace`. This branch already exists in [norm/model.py](norm/model.py) for `_setup_table`; registration piggybacks on it.
- Both `Table` and `View` subclasses are registered. `collect_models()` filters by base class when needed.

---

## Schema state model

Lives in `norm/migrations/state.py`. This is the in-memory representation of the entire DB schema — built by replaying migration files.

```python
@dataclass
class ColumnState:
    type: str                       # SQL type string — normalized: e.g. "BIGINT", never "BIGSERIAL"
    nullable: bool
    default: str | None             # raw SQL expression or None
    primary_key: bool = False
    _has_sequence_default: bool = False  # SERIAL/BIGSERIAL/SMALLSERIAL marker (see ADR-0004)

@dataclass
class TableState:
    columns: dict[str, ColumnState]
    constraints: list[dict]         # each dict has "type", "name", and type-specific keys
    indexes: list[dict]             # each dict has "name", "columns", "method", "unique"
    schema: str | None = None

@dataclass
class ViewState:
    definition: str                 # SQL produced by query.build()[0]
    columns: tuple[tuple[str, type], ...]  # for diff: column-list change → DROP+CREATE
    schema: str | None = None

@dataclass
class SchemaState:
    tables: dict[str, TableState]
    views: dict[str, ViewState]
    extensions: set[str]
    schemas: set[str]
```

SERIAL normalization rationale: see [ADR-0004](../docs/adr/0004-serial-normalized-in-schema-state.md).

---

## Schema metadata declarations

Extend `TableMeta` and `FieldDef` in [norm/model.py](norm/model.py). The existing `__meta__` attribute is kept — only the dataclass contents grow.

```python
@dataclass(frozen=True)
class ForeignKey:
    to: "Field[Any] | str"          # Field proxy (preferred) or "schema.table.column" string
    on_delete: str = "NO ACTION"    # CASCADE | SET NULL | RESTRICT | NO ACTION
    on_update: str = "NO ACTION"
    name: str | None = None         # auto-generated as "{table}_{column}_fkey" if None

@dataclass(frozen=True)
class IndexDef:
    columns: tuple[str, ...]
    unique: bool = False
    method: str | None = None       # BTREE | HASH | GIN | GIST — None = PG default
    partial: str | None = None      # WHERE clause for partial indexes
    name: str | None = None         # auto-generated if None

@dataclass(frozen=True)
class FieldDef:
    primary_key: bool = False
    db_default: bool = False        # SERIAL / server-side default — excluded from INSERT
    index: bool = False
    unique: bool = False
    name: str | None = None         # column name override
    fk: ForeignKey | None = None    # inline FK shortcut for single-column FKs

@dataclass(frozen=True)
class TableMeta:
    table: str | None = None
    schema: str | None = None
    indexes: tuple[IndexDef, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()    # composite FKs go here
    extensions: tuple[str, ...] = ()             # PG extensions required by this table
```

**Nullability** is derived solely from the type annotation: `Field[str]` is `NOT NULL`, `Field[str | None]` is nullable. `_parse_fields` already extracts the type via `typing.get_args`; extend it to detect `Union[X, None]` and strip the `None`. There is no `null` field on `FieldDef` — single source of truth.

**Identifier names** auto-generated when ≤ 63 chars (Postgres limit):
- Non-unique index: `idx_{table}_{cols joined by _}`
- Unique constraint: `{table}_{cols}_key`
- FK constraint: `{table}_{column}_fkey`

If the auto-generated name exceeds 63 chars, raise at metadata-validation time pointing the user at `name=`. No silent truncation.

---

## View declaration

Views are declared with a `query=` class kwarg captured by `NormMeta.__new__`. Users annotate the expected columns on the body for type-safety; `NormMeta` cross-validates names and `python_type` against `query.__columns__` and raises at class-creation time on any mismatch.

```python
class ActiveUsers(
    View,
    query=Users.select(Users.id, Users.email).where(Users.deleted_at.isnull()),
):
    id: PrimaryKey[int]
    email: Field[str]
```

Snapshot stores `cls.__view_query__.build()[0]` as `ViewState.definition` and the projected column list as `ViewState.columns`.

---

## DDL operation data classes

All live in `norm/migrations/operations.py`. Every operation implements:

- `apply(state: SchemaState) -> None` — mutates the in-memory schema state (for replay/diffing)
- `to_ddl() -> str` — returns the SQL string to execute

`RunSQL` and `RunPython` no-op on `apply` — they are data-only escape hatches (see "Escape hatches" below).

Reverse-op generation is handled by codegen at `make` time using `state_before`. Operations themselves do not know how to invert. See [ADR-0001](../docs/adr/0001-reverse-operations-as-explicit-list.md).

### Extension operations

```python
@dataclass
class CreateExtension:
    name: str
    # to_ddl: CREATE EXTENSION IF NOT EXISTS "name"
    # apply:  state.extensions.add(name)

@dataclass
class DropExtension:
    name: str
    # to_ddl: DROP EXTENSION IF EXISTS "name"
    # apply:  state.extensions.discard(name)
```

### Schema (namespace) operations

```python
@dataclass
class CreateSchema:
    name: str
    # to_ddl: CREATE SCHEMA IF NOT EXISTS "name"
    # apply:  state.schemas.add(name)

@dataclass
class DropSchema:
    name: str
    cascade: bool = False
    # to_ddl: DROP SCHEMA IF EXISTS "name" [CASCADE]
    # apply:  state.schemas.discard(name)
```

### Table operations

```python
@dataclass
class CreateTable:
    table: str
    columns: dict[str, ColumnDef]   # ordered; name → definition
    schema: str | None = None
    # to_ddl: CREATE TABLE IF NOT EXISTS "schema"."table" (col defs...)
    # apply:  state.tables[table] = TableState(columns=normalized..., schema=schema)
    #         SERIAL/BIGSERIAL/SMALLSERIAL in ColumnDef.type are normalized to INTEGER/BIGINT/SMALLINT
    #         with _has_sequence_default=True on the resulting ColumnState

@dataclass
class DropTable:
    table: str
    schema: str | None = None
    cascade: bool = False
    # to_ddl: DROP TABLE IF EXISTS "table" [CASCADE]
    # apply:  del state.tables[table]

@dataclass
class RenameTable:
    old_name: str
    new_name: str
    # to_ddl: ALTER TABLE "old" RENAME TO "new"
    # apply:  state.tables[new_name] = state.tables.pop(old_name)
```

### Column creation/removal

```python
@dataclass
class AddColumn:
    table: str
    column: str
    type: str
    nullable: bool
    default: str | None = None
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ADD COLUMN IF NOT EXISTS "col" TYPE [NOT NULL] [DEFAULT ...]
    # apply:  state.tables[table].columns[column] = ColumnState(...)
    # Note: NOT NULL without DEFAULT on a populated table will fail at apply.
    #       Codegen emits as-is; users fix by hand (see Open decisions resolved).

@dataclass
class DropColumn:
    table: str
    column: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" DROP COLUMN IF EXISTS "col"
    # apply:  del state.tables[table].columns[column]

@dataclass
class RenameColumn:
    table: str
    old_name: str
    new_name: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" RENAME COLUMN "old" TO "new"
    # apply:  state.tables[table].columns[new] = state.tables[table].columns.pop(old)
```

### Column modification (granular)

See [ADR-0002](../docs/adr/0002-granular-column-modification-ops.md). One op per `ALTER COLUMN` action — no bag-of-options dataclass.

```python
@dataclass
class AlterColumnType:
    table: str
    column: str
    type: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ALTER COLUMN "col" TYPE <type>
    # apply:  state.tables[table].columns[column].type = type

@dataclass
class SetColumnNotNull:
    table: str
    column: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ALTER COLUMN "col" SET NOT NULL
    # apply:  state.tables[table].columns[column].nullable = False

@dataclass
class DropColumnNotNull:
    table: str
    column: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ALTER COLUMN "col" DROP NOT NULL
    # apply:  state.tables[table].columns[column].nullable = True

@dataclass
class SetColumnDefault:
    table: str
    column: str
    default: str                    # raw SQL expression
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ALTER COLUMN "col" SET DEFAULT <default>
    # apply:  state.tables[table].columns[column].default = default

@dataclass
class DropColumnDefault:
    table: str
    column: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" ALTER COLUMN "col" DROP DEFAULT
    # apply:  state.tables[table].columns[column].default = None
```

### Constraint operations

Constraints are stored as typed dicts on `TableState.constraints`:

```python
# unique:      {"type": "unique",      "name": str, "columns": list[str]}
# foreign_key: {"type": "foreign_key", "name": str, "column": str,
#               "references_table": str, "references_column": str,
#               "references_schema": str|None, "on_delete": str, "on_update": str}

@dataclass
class AddConstraint:
    table: str
    constraint: dict                # one of the shapes above
    schema: str | None = None
    # to_ddl: wrapped in DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL END $$
    #         for idempotency
    # apply:  state.tables[table].constraints.append(normalized_constraint)

@dataclass
class DropConstraint:
    table: str
    name: str
    schema: str | None = None
    # to_ddl: ALTER TABLE "table" DROP CONSTRAINT IF EXISTS "name"
    # apply:  removes matching entry from state.tables[table].constraints
```

### Index operations

Production-safe defaults — see [ADR-0003](../docs/adr/0003-concurrent-index-defaults.md).

```python
@dataclass
class CreateIndex:
    table: str
    columns: list[str]
    name: str | None = None         # auto-generated; fails loudly when > 63 chars
    method: str | None = None       # BTREE | GIN | GIST | HASH
    unique: bool = False
    concurrent: bool = True         # DEFAULT TRUE — implies atomic=False on containing migration
    schema: str | None = None
    # to_ddl: CREATE [UNIQUE] INDEX [CONCURRENTLY] IF NOT EXISTS "name" ON "table" [USING method] (cols)
    # apply:  state.tables[table].indexes.append({"name": ..., "columns": ..., "method": ..., "unique": ...})

@dataclass
class DropIndex:
    name: str
    concurrent: bool = True         # DEFAULT TRUE
    schema: str | None = None
    # to_ddl: DROP INDEX [CONCURRENTLY] IF EXISTS "name"
    # apply:  removes matching entry from all tables' indexes lists
```

### View operations

```python
@dataclass
class CreateView:
    name: str
    definition: str                 # the SELECT body (without CREATE VIEW prefix)
    schema: str | None = None
    replace: bool = True            # use CREATE OR REPLACE VIEW
    # to_ddl: CREATE [OR REPLACE] VIEW "schema"."name" AS <definition>
    # apply:  state.views[name] = ViewState(definition=..., columns=..., schema=schema)

@dataclass
class DropView:
    name: str
    schema: str | None = None
    cascade: bool = False
    # to_ddl: DROP VIEW IF EXISTS "name" [CASCADE]
    # apply:  del state.views[name]
```

Diff strategy: if `ViewState.columns` is unchanged but `definition` differs → `CreateView(replace=True)`. If the column list changed (names, types, or order) → emit `DropView` + `CreateView`, because Postgres's `CREATE OR REPLACE VIEW` rejects column-list reshapes.

### Escape hatches (data-only)

```python
@dataclass
class RunSQL:
    sql: str                            # single statement or multiple separated by ";"
    reverse_sql: str | None = None
    # to_ddl: returns sql as-is
    # apply:  no-op (runner splits on ";" and executes each individually)
    # check: lints sql for DDL keywords (ALTER/CREATE/DROP/TRUNCATE) → warning

@dataclass
class RunPython:
    fn: Callable[[AsyncConnection], Awaitable[None]]
    reverse_fn: Callable[[AsyncConnection], Awaitable[None]] | None = None
    # apply:  no-op (runner calls fn(conn) directly)
```

`fn` and `reverse_fn` receive the norm `AsyncConnection` wrapper, not a raw asyncpg connection. Schema changes must use the DDL ops above — `RunSQL`/`RunPython` are for data backfills and seeding.

### `ColumnDef` (helper for `CreateTable`)

```python
@dataclass
class ColumnDef:
    type: str                       # SQL type string; SERIAL macros allowed and normalized in state
    nullable: bool = True
    default: str | None = None      # raw SQL expression
    primary_key: bool = False
```

### Python → SQL type mapping

| Python type | SQL type |
|---|---|
| `int` (plain) | `BIGINT` |
| `int` + `primary_key=True, db_default=True` | `BIGSERIAL` |
| `str` | `TEXT` |
| `float` | `DOUBLE PRECISION` |
| `bool` | `BOOLEAN` |
| `datetime` | `TIMESTAMPTZ` |
| `date` | `DATE` |
| `Decimal` | `NUMERIC` |
| `uuid.UUID` | `UUID` |
| `dict` / `list` (any parameterization) | `JSONB` |
| `bytes` | `BYTEA` |
| `X \| None` | type of `X` + nullable=True |

`int` defaults to `BIGINT` (not `INTEGER`) for forward-compat. Type-parameters on `dict[K, V]` and `list[T]` are advisory only — they don't affect SQL. Custom `db_type` override on `FieldDef` is deferred.

---

## Snapshot: models → SchemaState

`norm/migrations/snapshot.py` converts migration-eligible models from `_MODEL_REGISTRY` into a `SchemaState`. This is the **target state** used by `diff_states`.

```python
def models_to_schema_state(models: list[type]) -> SchemaState:
    ...
```

Per `Table` model:

- `cls.__table__` → table name (via `pypika.Table.get_table_name()`)
- `cls.__meta__.schema` → schema
- `cls.__fields__` → for each Field proxy: column name, Python type, `FieldDef` → `ColumnState`. Nullability is derived from the `Field[X | None]` form during `_parse_fields`.
- `cls.__meta__.indexes` → `TableState.indexes`
- `cls.__meta__.foreign_keys` → `"foreign_key"` constraint dicts
- `cls.__meta__.extensions` → `SchemaState.extensions`
- Field-level `FieldDef.unique=True` → `"unique"` constraint dict
- Field-level `FieldDef.index=True` → index entry
- Field-level `FieldDef.fk` → FK constraint dict (target resolved via `Field` proxy or string)

Per `View` model: `cls.__view_query__.build()[0]` is the definition string; `ViewState.columns` is built from the query's `__columns__`.

---

## Replay

`norm/migrations/replay.py` — builds `SchemaState` from existing migration files:

```python
def replay_migrations(paths: Iterable[Path]) -> SchemaState:
    state = SchemaState(tables={}, views={}, extensions=set(), schemas=set())
    for path in sorted(paths, key=lambda p: p.name):
        migration_cls = _load_migration(path)
        for op in migration_cls.operations:
            op.apply(state)
    return state
```

This is the **current state** — what the DB looks like if all migrations have been applied.

---

## Diff

`norm/migrations/draft.py` — compares current (replayed) state against target (model snapshot):

```python
def diff_states(current: SchemaState, target: SchemaState) -> tuple[list[Any], list[Any]]:
    """Returns (forward_ops, reverse_ops). reverse_ops is the literal inverse list,
    built from current state values, suitable for direct use as Migration.reverse_operations."""
    ...
```

Forward order:

1. Extensions to create / drop
2. Schemas to create
3. New tables (`CreateTable`) — FK constraints deferred until after all tables exist
4. Deferred FK `AddConstraint`
5. Dropped tables (`DropTable`)
6. Existing tables — column adds/drops, granular column modifications, constraint adds/drops, index creates/drops
7. New views (`CreateView`) / dropped views (`DropView`)

Reverse order: the inverse of the above, with each forward op paired to its inverse computed from `current` state values (so `DropColumn` reverses to a complete `AddColumn` with the original type/nullable/default; `AlterColumnType` reverses to `AlterColumnType` with the previous type; etc.).

---

## Migration file format

Codegen passes **every field by keyword, including defaults** — the file is self-documenting:

```python
# migrations/0001_initial.py
from norm.migrations import Migration
from norm.migrations.operations import (
    CreateExtension, CreateSchema, CreateTable, ColumnDef,
    AddConstraint, CreateIndex, CreateView, RunSQL, RunPython,
)

class Migration(Migration):
    name = "0001_initial"
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction
    atomic = False
    dependencies: list[str] = []

    operations = [
        CreateExtension(name="pgcrypto"),
        CreateSchema(name="audit"),
        CreateTable(
            table="users",
            schema="public",
            columns={
                "id":    ColumnDef(type="BIGSERIAL", nullable=False, primary_key=True),
                "email": ColumnDef(type="TEXT", nullable=False),
            },
        ),
        AddConstraint(
            table="users",
            constraint={"type": "unique", "name": "users_email_key", "columns": ["email"]},
        ),
        CreateIndex(
            table="users",
            columns=["email"],
            name="idx_users_email",
            method=None,
            unique=False,
            concurrent=True,
        ),
    ]

    reverse_operations = [
        DropIndex(name="idx_users_email", concurrent=True),
        DropConstraint(table="users", name="users_email_key"),
        DropTable(table="users", schema="public"),
        DropSchema(name="audit"),
        DropExtension(name="pgcrypto"),
    ]
```

`reverse_operations`:
- `None` (or attribute absent) → migration is non-reversible; rollback raises pointing at the file
- `[]` → explicit no-op reverse (e.g. for backfill-only migrations)
- non-empty list → executed in given order on rollback

`atomic`:
- `True` (default) → BEGIN/COMMIT around the migration
- `False` → no transaction; required if any op is non-transactional. Codegen sets it automatically with a one-line comment explaining why.

Migration `name` is the filename stem (without `.py`).

---

## `norm_migrations` tracking table

Created automatically on first `apply` if absent:

```sql
CREATE TABLE IF NOT EXISTS norm_migrations (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## CLI commands

Three entry points exposed via `python -m norm.migrations`.

### Configuration

`pyproject.toml`:

```toml
[tool.norm]
migrations_dir = "migrations"           # default
models = ["myapp.models"]               # importable module paths
```

If `[tool.norm]` is absent or omits `models`, the CLI falls back to convention: look for a `models.py` or `models/` package at CWD. All three commands accept `--migrations-dir DIR` and `--models pkg1,pkg2,...` overrides.

### 1. `make` — generate a migration file

```
python -m norm.migrations make [--label LABEL] [--migrations-dir DIR] [--models pkg1,...]
```

Steps:

1. Import configured/conventional model modules → populates `_MODEL_REGISTRY`
2. `replay_migrations(existing_files)` → `current: SchemaState`
3. `models_to_schema_state(collect_models())` → `target: SchemaState`
4. `diff_states(current, target)` → `(forward, reverse)`
5. If both empty → print "No changes detected." and exit 0
6. If any op is non-transactional → set `atomic = False`, prepend explanatory comment
7. Determine label:
   - `--label` if provided
   - 1 op → derive from op (`create_users`, `add_email_to_users`, `drop_orders_table`, `index_users_email`)
   - 2-3 ops on same table → `alter_<table>`
   - otherwise → `auto`
8. Write `NNNN_<label>.py` with all fields passed by keyword → print path and exit 0

### 2. `apply` — run unapplied migrations against the DB

```
python -m norm.migrations apply [--migrations-dir DIR] [--db-url URL]
```

Apply loop (per pending migration, in dependency order):

1. If `atomic = True`: `BEGIN`
2. For each op:
   - `RunPython` → `await op.fn(conn)` where `conn` is `norm.AsyncConnection`
   - `RunSQL` → split on `;` and execute each statement
   - DDL → `await conn.execute(op.to_ddl())`
3. `INSERT INTO norm_migrations (name) VALUES ($1)`
4. If `atomic = True`: `COMMIT`

On failure inside a `CONCURRENTLY` index op, print the recovery command (`DROP INDEX CONCURRENTLY IF EXISTS ...`) and re-raise. The tracking row is not inserted; retry after manual cleanup.

Rollback (via `MigrationRunner.rollback(name)`):

1. Refuse unless `name` is the most-recently-applied migration, or `--force` is passed
2. Refuse if `reverse_operations is None` (non-reversible)
3. If `atomic = True`: `BEGIN`
4. For each op in `reverse_operations` (in given order): execute via the same dispatch as apply
5. `DELETE FROM norm_migrations WHERE name = $1`
6. If `atomic = True`: `COMMIT`

### 3. `check` — lint migrations (safe for pre-commit hooks)

```
python -m norm.migrations check [--migrations-dir DIR] [--models pkg1,...]
```

No DB connection required. Exits non-zero if any of:

- A migration file fails to import
- Any operation is missing `apply` or `to_ddl` (structural check via `hasattr`)
- `replay_migrations` raises `SchemaError` (e.g. `AddColumn` on a non-existent table)
- A migration with non-transactional ops has `atomic = True`
- `diff_states(replayed, models_to_schema_state(collect_models()))` produces ops — meaning there are model changes without a corresponding migration file
- `RunSQL.sql` contains DDL keywords (ALTER/CREATE/DROP/TRUNCATE) — warning (non-zero exit)

Prints a per-file summary on success, or the first error with file + line on failure. Exits 0 silently when everything is in sync.

---

## Public API

```python
from norm.migrations import (
    Migration,
    MigrationRunner,
    collect_models,     # returns migration-eligible Table and View subclasses
)
from norm.migrations.codegen import make_migration
```

```python
runner = MigrationRunner(
    conn=conn,                                  # norm.AsyncConnection
    migrations_dir="migrations",
    migrations_table="norm_migrations",
)

await runner.apply()                            # list[str] of applied names
await runner.rollback("0002_...", force=False)  # reverse a specific migration
pending = await runner.pending()                # list[str] of unapplied names
applied = await runner.applied()                # list[str] of applied names
```

---

## File layout

```
norm/migrations/
    __init__.py         # public re-exports: Migration, MigrationRunner, collect_models
    __main__.py         # CLI: make | apply | check
    state.py            # SchemaState, TableState, ViewState, ColumnState, SchemaError
    operations.py       # all operation dataclasses (apply + to_ddl)
    replay.py           # replay_migrations()
    snapshot.py         # models_to_schema_state() — norm model → SchemaState bridge
    draft.py            # diff_states() — returns (forward, reverse) tuple
    runner.py           # MigrationRunner
    registry.py         # collect_models(), _MODEL_REGISTRY reference
    codegen.py          # make_migration()
    config.py           # pyproject.toml [tool.norm] loader + conventional fallback
```

---

## Acceptance criteria

- [ ] `CreateExtension`, `DropExtension`, `CreateSchema`, `DropSchema` exist and correctly mutate `SchemaState`
- [ ] `CreateTable`, `DropTable`, `RenameTable` exist with correct `apply` and `to_ddl`
- [ ] `CreateTable.apply` normalizes `SERIAL`/`BIGSERIAL`/`SMALLSERIAL` to underlying int type + `_has_sequence_default=True`
- [ ] `AddColumn`, `DropColumn`, `RenameColumn` exist with correct `apply` and `to_ddl`
- [ ] Granular `AlterColumnType`, `SetColumnNotNull`, `DropColumnNotNull`, `SetColumnDefault`, `DropColumnDefault` exist with correct `apply` and `to_ddl`
- [ ] `AddConstraint`, `DropConstraint` handle `unique` and `foreign_key` types; `AddConstraint.to_ddl` is wrapped in a `DO $$ ... EXCEPTION` block
- [ ] `CreateIndex` and `DropIndex` default to `concurrent=True`; `to_ddl` emits `CONCURRENTLY` accordingly
- [ ] `CreateView`, `DropView` exist with correct `apply` and `to_ddl`
- [ ] `RunSQL` and `RunPython` no-op on `apply`
- [ ] `replay_migrations(paths)` reduces all files into a final `SchemaState`
- [ ] `_MODEL_REGISTRY` is populated by `NormMeta.__new__` when `__table__` is not in the class namespace; both `Table` and `View` subclasses register; clones/aliases/set-ops do not
- [ ] `View` subclasses declared via `class X(View, query=...)` capture `__view_query__` on the class; annotation/query cross-validation raises at class creation on mismatch
- [ ] `models_to_schema_state(models)` produces correct `SchemaState` from `Table` and `View` subclasses; nullability is derived from `Field[X | None]`
- [ ] `diff_states(current, target)` detects: new/dropped tables, new/dropped columns, granular column modifications, new/dropped indexes, new/dropped constraints, new/dropped views (with column-list change → DROP+CREATE), new/dropped extensions
- [ ] `diff_states` returns `(forward, reverse)` and the reverse list correctly inverts each forward op using `current`-state values
- [ ] FK `AddConstraint` ops are deferred until after all `CreateTable` ops in the forward output
- [ ] `collect_models()` returns only registry-eligible models; clones/aliases/set-ops are never returned
- [ ] Codegen writes both `operations` and `reverse_operations` with every field passed by keyword (including defaults)
- [ ] Codegen sets `atomic = False` and prepends a one-line explanatory comment when any op is non-transactional
- [ ] Codegen rejects long identifiers (> 63 chars) with a clear error pointing at `name=`
- [ ] `make` command writes a valid importable `.py` file and prints the path; prints "No changes" and exits 0 when nothing changed; derives filename label from diff content when `--label` is omitted
- [ ] `apply` command creates `norm_migrations` if absent and applies pending in dependency order; passes `norm.AsyncConnection` to `RunPython.fn`
- [ ] `apply` prints recovery instructions and re-raises on `CONCURRENTLY` failure
- [ ] `rollback(name)` refuses unless name is most-recently-applied or `--force` is passed; refuses when `reverse_operations is None`; executes `reverse_operations` in order; removes the tracking row
- [ ] `check` exits non-zero on import failure, structural op-shape errors, `SchemaError` during replay, missing migrations, or `atomic=True` with non-transactional ops; warns (non-zero) on DDL keywords inside `RunSQL.sql`
- [ ] `check` exits 0 with no output when everything is in sync (safe for pre-commit)
- [ ] Unit tests assert exact SQL strings for each operation's `to_ddl()`
- [ ] Unit tests assert correct `SchemaState` mutations for each operation's `apply()`
- [ ] Integration test: fresh DB → `apply` → assert `norm_migrations` rows → `rollback` → assert rows removed

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip

## Open decisions resolved (this session)

1. **Migration directory layout** — flat (`migrations/0001_initial.py`); one set per `pyproject.toml`; cross-project FK references are user responsibility.
2. **`RunPython` connection type** — norm `AsyncConnection` wrapper (driver-abstracted for future drivers).
3. **`check` model discovery** — `[tool.norm] models = [...]` in `pyproject.toml`; falls back to `models.py`/`models/` in CWD; `--models` CLI override.
4. **View diffing** — string equality on `ViewState.definition`; column-list changes (names/types/order) emit DROP+CREATE; same-shape changes use `CREATE OR REPLACE VIEW`.
5. **SERIAL normalization** — normalized in state to underlying int type + `_has_sequence_default` flag; DDL still emits `BIGSERIAL`. See [ADR-0004](../docs/adr/0004-serial-normalized-in-schema-state.md).

## Related ADRs

- [ADR-0001 — Reverse operations as explicit list](../docs/adr/0001-reverse-operations-as-explicit-list.md)
- [ADR-0002 — Granular column modification ops](../docs/adr/0002-granular-column-modification-ops.md)
- [ADR-0003 — Concurrent index defaults](../docs/adr/0003-concurrent-index-defaults.md)
- [ADR-0004 — SERIAL normalized in schema state](../docs/adr/0004-serial-normalized-in-schema-state.md)
