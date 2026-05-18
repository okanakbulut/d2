# 143 — Constraints + indexes with `concurrent=True` default and auto `atomic=False`

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

Unique constraints and indexes (non-FK), with production-safe defaults per [ADR-0003](../docs/adr/0003-concurrent-index-defaults.md). After this slice, a user can mark fields `Field[str] = field(unique=True)` or `field(index=True)`, declare `TableMeta(indexes=(IndexDef(...),))`, and `make` produces correctly-ordered ops with `concurrent=True` defaults and a non-atomic migration.

### Scope

- **Operations**:
  - `AddConstraint(table, constraint, schema)` where `constraint` is the unique dict shape (FK shape exists but is exercised in 144). `to_ddl()` wraps the `ALTER TABLE ... ADD CONSTRAINT` in `DO $$ BEGIN ... EXCEPTION WHEN duplicate_object THEN NULL END $$` for idempotency.
  - `DropConstraint(table, name, schema)` — straightforward.
  - `CreateIndex(table, columns, name, method, unique, concurrent=True, schema=None)` — default `concurrent=True`, emits `CREATE [UNIQUE] INDEX [CONCURRENTLY] IF NOT EXISTS ...`.
  - `DropIndex(name, concurrent=True, schema=None)` — default `concurrent=True`.
- **Metadata**: extend `TableMeta` with `indexes: tuple[IndexDef, ...] = ()`. Extend `FieldDef` (already has `unique`, `index`) — snapshot translates these to constraint dicts and index entries.
- **Identifier-length validation**: codegen / metadata validation raises when auto-generated name > 63 chars, pointing user at `name=`. Auto-naming rules: `idx_{table}_{cols}` for non-unique indexes, `{table}_{cols}_key` for unique constraints.
- **Diff**: detects index and unique-constraint adds/drops between `current` and `target`.
- **Codegen non-atomic handling**: when any op in the generated migration is non-transactional (any `CreateIndex(concurrent=True)` or `DropIndex(concurrent=True)`), codegen sets `atomic = False` on the Migration class and prepends a one-line explanatory comment.
- **Runner**: when `atomic = False`, do NOT wrap in BEGIN/COMMIT. On failure inside `CONCURRENTLY` op, print the exact `DROP INDEX CONCURRENTLY IF EXISTS <name>;` recovery command and re-raise without recording the migration.
- **check**: warns (non-zero exit) when a migration with non-transactional ops has `atomic = True`.

Out of scope: FK constraints (144); composite unique constraints via `TableMeta` (basic single-column unique only here; composite via `IndexDef(unique=True)` is supported as a side effect).

## Acceptance criteria

- [ ] `AddConstraint`, `DropConstraint`, `CreateIndex`, `DropIndex` exist with correct `apply` and `to_ddl`
- [ ] `AddConstraint.to_ddl()` wraps in `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL END $$`
- [ ] `CreateIndex.concurrent` and `DropIndex.concurrent` default to `True`
- [ ] `to_ddl()` emits `CONCURRENTLY` correctly for both create and drop
- [ ] `TableMeta.indexes` accepted and reflected in `models_to_schema_state`
- [ ] `FieldDef.unique=True` and `index=True` produce correct constraint/index entries in the snapshot
- [ ] Auto-naming: indexes `idx_{table}_{cols}`, unique constraints `{table}_{cols}_key`
- [ ] Identifier-length validation raises with a clear message pointing at `name=` when > 63 chars
- [ ] Codegen sets `atomic = False` with explanatory comment when any op is non-transactional
- [ ] Codegen writes every field by keyword (including `concurrent=True`, `unique=False`, etc.)
- [ ] Runner does not wrap non-atomic migrations in BEGIN/COMMIT
- [ ] Runner prints recovery instructions and re-raises on `CONCURRENTLY` failure
- [ ] `check` exits non-zero when a migration with non-transactional ops has `atomic = True`
- [ ] Unit tests assert exact `to_ddl()` strings and `apply()` state mutations
- [ ] Integration test: model with `unique=True` and `IndexDef`, run `make` → migration is `atomic=False` with `concurrent=True`; `apply` succeeds

## Blocked by

- [142 — Column ops: Add/Drop/Rename + granular column modifications](142-column-ops-add-drop-rename-and-granular-modify.md)
