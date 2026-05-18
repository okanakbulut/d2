# 146 — Extensions + schemas (namespace) operations

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

Lifecycle for Postgres extensions and namespace schemas. After this slice, a user can declare `TableMeta(extensions=("pgcrypto", "uuid-ossp"))` on a model, declare a schema name on `TableMeta`, and `make` produces correctly-ordered `CreateExtension` and `CreateSchema` ops before any `CreateTable` that depends on them.

### Scope

- **Operations**:
  - `CreateExtension(name)` / `DropExtension(name)` — `CREATE EXTENSION IF NOT EXISTS "name"` / `DROP EXTENSION IF EXISTS "name"`
  - `CreateSchema(name)` / `DropSchema(name, cascade=False)` — `CREATE SCHEMA IF NOT EXISTS "name"` / `DROP SCHEMA IF EXISTS "name" [CASCADE]`
- **State**: `SchemaState.extensions: set[str]` and `SchemaState.schemas: set[str]` already exist from 140; this slice wires them through the snapshot, diff, and codegen.
- **Snapshot**: walks all models, unions `cls.__meta__.extensions` into `state.extensions`; collects unique `cls.__meta__.schema` values (excluding `None` and `"public"`) into `state.schemas`.
- **Diff**: emits `CreateExtension` for added, `DropExtension` for removed; same for `CreateSchema` / `DropSchema`. Forward ordering:
  1. Extensions (extensions can be required by index methods like GIN — must exist first)
  2. Schemas
  3. Tables (from 141)
  4. FKs (from 144)
- **Codegen**: writes extension and schema ops with all fields by keyword.

Out of scope: extension version pinning, `WITH SCHEMA` clause for extensions, schema renames.

## Acceptance criteria

- [ ] `CreateExtension`, `DropExtension`, `CreateSchema`, `DropSchema` exist with correct `apply` and `to_ddl`
- [ ] `TableMeta.extensions` already exists on the dataclass (verify it's wired)
- [ ] Snapshot unions extensions across all models; collects schemas from `cls.__meta__.schema` (excluding `None` and `"public"`)
- [ ] Diff emits create/drop ops for extensions and schemas correctly
- [ ] Forward ordering in diff: extensions → schemas → tables → FKs
- [ ] Codegen writes ops with all fields by keyword
- [ ] Reverse ops: `CreateExtension` → `DropExtension`; `CreateSchema` → `DropSchema(cascade=False)`
- [ ] Unit tests assert exact `to_ddl()` strings and `apply()` state mutations
- [ ] Integration test: model declares `extensions=("pgcrypto",)` and `schema="audit"`; `make` produces correctly-ordered migration; `apply` succeeds

## Blocked by

- [141 — Model snapshot + diff + codegen + CLI for tables](141-snapshot-diff-codegen-cli-for-tables.md)
