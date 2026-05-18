# 140 — Tracer: hand-written CreateTable migration through `apply`

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

The thinnest possible cut through the migration runner spine, so subsequent slices have a working backbone to extend. After this slice, a user can:

1. Hand-write a migration file `migrations/0001_initial.py` containing a `Migration` subclass with a single `CreateTable` op
2. Construct a `MigrationRunner(conn=..., migrations_dir="migrations")` and `await runner.apply()` against a real Postgres instance
3. Observe that the table was created and a row in `norm_migrations` records the applied name
4. Re-run `apply()` and observe the migration is skipped (already applied)

No diff, no codegen, no CLI in this slice — those are 141+. This slice exists only to prove that the state model, `CreateTable.apply` + `to_ddl`, the `Migration` class shape, and the runner's apply loop work end-to-end against Postgres.

### Scope

- `norm/migrations/state.py`: `SchemaState`, `TableState`, `ColumnState`, `SchemaError`. Only the `tables` field on `SchemaState` is used in this slice; `views`/`extensions`/`schemas` are present but empty.
- `norm/migrations/operations.py`: `CreateTable`, `ColumnDef` only. Both implement `apply(state)` and `to_ddl()`. SERIAL normalization in `CreateTable.apply` per [ADR-0004](../docs/adr/0004-serial-normalized-in-schema-state.md).
- `norm/migrations/__init__.py`: `Migration` base class with `name`, `operations`, `reverse_operations = None`, `dependencies: list[str] = []`, `atomic: bool = True`.
- `norm/migrations/runner.py`: `MigrationRunner` with `apply()`, `applied()`, `pending()`. Creates `norm_migrations` table if absent. Applies pending migrations in name-sorted order. Wraps each in BEGIN/COMMIT when `atomic=True`. Uses norm `AsyncConnection`.
- `norm/migrations/replay.py`: minimal `_load_migration(path) -> type[Migration]` loader.

Out of scope: all other ops, diff, snapshot, codegen, CLI, rollback, dependencies graph (just sort by name for now).

## Acceptance criteria

- [ ] `SchemaState`, `TableState`, `ColumnState`, `SchemaError` exist in `norm/migrations/state.py`
- [ ] `CreateTable.to_ddl()` produces exact `CREATE TABLE IF NOT EXISTS "schema"."table" (...)` SQL; column DDL emits `BIGSERIAL` when requested
- [ ] `CreateTable.apply(state)` normalizes `SERIAL`/`BIGSERIAL`/`SMALLSERIAL` to `INTEGER`/`BIGINT`/`SMALLINT` with `_has_sequence_default=True`
- [ ] `Migration` base class has `name`, `operations`, `reverse_operations`, `dependencies`, `atomic` attributes
- [ ] `MigrationRunner.apply()` creates `norm_migrations` table if absent (idempotent)
- [ ] `MigrationRunner.apply()` loads migrations from `migrations_dir`, sorts by filename, executes pending only, wraps each in transaction when `atomic=True`, records each in `norm_migrations`
- [ ] `MigrationRunner.applied()` / `pending()` return correct name lists
- [ ] Re-running `apply()` is a no-op when nothing is pending
- [ ] Unit test: `CreateTable.to_ddl()` returns the exact expected SQL string
- [ ] Unit test: `CreateTable.apply(state)` produces the expected `TableState` with normalized types
- [ ] Integration test against real Postgres: hand-written migration file → `apply` → table exists, `norm_migrations` row present → second `apply` is a no-op

## Blocked by

- [01 — Tracer: end-to-end SELECT round-trip](01-tracer-select-roundtrip.md)
