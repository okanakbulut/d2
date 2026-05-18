# 142 — Column ops: Add/Drop/Rename + granular column modifications

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

The column lifecycle. After this slice, a user can add, drop, rename, retype, change nullability, and set/drop defaults on columns of existing tables — and `make` produces the right ops automatically.

### Scope

- **Operations** in `norm/migrations/operations.py`:
  - `AddColumn(table, column, type, nullable, default=None, schema=None)`
  - `DropColumn(table, column, schema=None)`
  - `RenameColumn(table, old_name, new_name, schema=None)`
  - Granular modify ops per [ADR-0002](../docs/adr/0002-granular-column-modification-ops.md):
    - `AlterColumnType(table, column, type, schema=None)`
    - `SetColumnNotNull(table, column, schema=None)`
    - `DropColumnNotNull(table, column, schema=None)`
    - `SetColumnDefault(table, column, default, schema=None)`
    - `DropColumnDefault(table, column, schema=None)`
  - Each with `apply(state)` mutating the right `ColumnState` and `to_ddl()` emitting one `ALTER TABLE ... ALTER COLUMN ...` statement.
- **Diff**: `diff_states` extended to emit column adds/drops, and granular modifications when type / nullability / default differ between `current` and `target` columns.
- **Codegen**: writes correct forward and reverse ops. Reverse for `DropColumn` reads `current` state to reconstruct a full `AddColumn(type=..., nullable=..., default=...)`. Reverse for each granular op mirrors with the previous value.
- **AddColumn NOT NULL without default**: emit DDL as-is per parent issue's resolved decisions. Fails loud at apply; user fixes the migration file by hand.

Out of scope: constraints (143), indexes (143), FKs (144), schema/extension changes (146).

## Acceptance criteria

- [ ] `AddColumn`, `DropColumn`, `RenameColumn` exist with correct `apply` and `to_ddl`
- [ ] All five granular modify ops exist with correct `apply` and `to_ddl`
- [ ] Each `to_ddl()` returns a single `ALTER TABLE ... ALTER COLUMN ...` statement (no combined multi-action form)
- [ ] `diff_states` produces `AddColumn` when a new field is in `target` but not `current`
- [ ] `diff_states` produces `DropColumn` when a field is in `current` but not `target`
- [ ] `diff_states` produces granular modify ops only for the fields that actually changed (type-only diff emits only `AlterColumnType`; nullable-only diff emits only `Set/DropColumnNotNull`; etc.)
- [ ] Codegen pairs each forward op with a correct reverse op using `current`-state values
- [ ] `RenameColumn` is NOT auto-emitted by diff (rename detection is non-trivial — out of scope); users hand-edit migrations to use it
- [ ] Unit tests assert exact `to_ddl()` strings and `apply()` state mutations for every op
- [ ] Integration test: declare a model, apply, add a field, `make` + `apply` again, observe column exists with correct type/nullability/default

## Blocked by

- [141 — Model snapshot + diff + codegen + CLI for tables](141-snapshot-diff-codegen-cli-for-tables.md)
