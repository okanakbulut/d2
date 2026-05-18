# 147 — Reverse operations codegen + `rollback`

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

The complete rollback story per [ADR-0001](../docs/adr/0001-reverse-operations-as-explicit-list.md). Earlier slices (140-146) emit `reverse_operations` lists at codegen time, but only for ops they introduce. This slice ensures every op has a documented reverse, the runner can execute `reverse_operations` literally, and `rollback(name)` enforces the safety policy.

### Scope

- **Codegen reverse completeness**: every DDL op produced by `diff_states` has its inverse paired in the same migration's `reverse_operations` list, computed from `current`-state values. Specifically:
  - `CreateTable` ↔ `DropTable`
  - `AddColumn` ↔ `DropColumn` (forward and reverse known from target/current respectively)
  - `DropColumn` reverse is a full `AddColumn(type=..., nullable=..., default=...)` reconstructed from `current` state
  - `AlterColumnType` reverse is `AlterColumnType` with previous type
  - `SetColumnNotNull` ↔ `DropColumnNotNull`
  - `SetColumnDefault` ↔ `DropColumnDefault(...)` or `SetColumnDefault(previous_default)` as appropriate
  - `RenameColumn` reverse swaps `old_name` ↔ `new_name`
  - `AddConstraint` ↔ `DropConstraint(table, name)`
  - `CreateIndex` ↔ `DropIndex(name, concurrent=...)`
  - `CreateExtension` ↔ `DropExtension`
  - `CreateSchema` ↔ `DropSchema`
  - `CreateView` ↔ `DropView` (or reverse `CreateView(replace=True)` with previous definition)
- **`MigrationRunner.rollback(name, force=False)`**:
  - Refuse unless `name` is the most-recently-applied migration, OR `force=True`
  - Refuse if `reverse_operations is None` — raise pointing at the file
  - `reverse_operations == []` is a valid no-op rollback
  - If `atomic = True`: wrap in BEGIN/COMMIT
  - For each op in `reverse_operations` (in given order): dispatch via the same logic as `apply` (RunPython → `await fn(conn)`, RunSQL → split, DDL → `await conn.execute(to_ddl())`)
  - `DELETE FROM norm_migrations WHERE name = $1`
- **CLI**: `python -m norm.migrations rollback NAME [--force]` subcommand wired to the runner.

Out of scope: rollback chains (multiple migrations at once), partial rollback, `unapply` semantics.

## Acceptance criteria

- [ ] Codegen produces a complete `reverse_operations` list for every diff-emitted op (full coverage of DDL ops introduced by 140-146)
- [ ] `DropColumn` reverse reconstructs full `AddColumn` from `current.tables[t].columns[c]` (type, nullable, default)
- [ ] `AlterColumnType` reverse uses the previous type from `current` state
- [ ] `MigrationRunner.rollback(name)` refuses unless `name` is most-recently-applied or `force=True`
- [ ] `rollback` refuses when `reverse_operations is None` with a clear error message
- [ ] `rollback` executes `reverse_operations` in given order through the same dispatch as `apply`
- [ ] `rollback` removes the row from `norm_migrations` on success
- [ ] `rollback` honors `atomic` flag (transaction wrapping)
- [ ] CLI `rollback NAME [--force]` subcommand exists and dispatches to runner
- [ ] Unit test: codegen emits correct reverse op for each DDL forward op
- [ ] Integration test: declare model, `make` + `apply`, modify model, `make` + `apply`, then `rollback` the second migration → schema reverts, tracking row removed
- [ ] Integration test: `rollback` on a non-most-recent migration without `--force` → refuses with clear message

## Blocked by

- [142 — Column ops: Add/Drop/Rename + granular column modifications](142-column-ops-add-drop-rename-and-granular-modify.md)
- [143 — Constraints + indexes with `concurrent=True` default and auto `atomic=False`](143-constraints-and-indexes-concurrent-defaults.md)
- [144 — Foreign keys: inline + table-level, Field-proxy targeting, deferred ordering](144-foreign-keys.md)
- [145 — `View(query=...)` declaration + view ops + view diff strategy](145-views-query-kwarg-and-diff.md)
- [146 — Extensions + schemas (namespace) operations](146-extensions-and-schemas.md)
