# 144 — Foreign keys: inline + table-level, Field-proxy targeting, deferred ordering

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

Foreign-key support across declaration, snapshot, diff, and codegen. After this slice, a user can:

- Declare a single-column FK inline: `org_id: Field[int] = field(fk=ForeignKey(to=Organization.id, on_delete="CASCADE"))`
- Declare composite or multi-FK tables via `TableMeta(foreign_keys=(ForeignKey(...), ForeignKey(...)))`
- Run `make` and get a migration where `AddConstraint` ops for FKs come after all `CreateTable` ops (deferred ordering) so target tables exist when the FK is added.

### Scope

- **`ForeignKey` dataclass** in [norm/model.py](norm/model.py): `to: Field[Any] | str`, `on_delete`, `on_update`, `name`. The `to` field accepts a `Field` proxy (preferred — refactor-safe, type-checked) or a `"schema.table.column"` string (for forward refs or tables outside norm). FK auto-name: `{table}_{column}_fkey` when not provided.
- **Snapshot**: resolves `ForeignKey.to`:
  - When it's a `Field` proxy: derive `references_table`, `references_column`, `references_schema` from `proxy.pika_field.table`. The proxy already carries this — no new infrastructure needed.
  - When it's a string: parse `"schema.table.column"` (or `"table.column"`).
  - Produce a `"foreign_key"` constraint dict with `references_table`, `references_column`, `references_schema`, `on_delete`, `on_update`.
- **`FieldDef.fk`** is the inline shortcut; `TableMeta.foreign_keys` collects table-level FKs. Both emit identical constraint dicts.
- **Diff**: detects FK adds/drops. Forward order in `diff_states`:
  1. Extensions/schemas (later slices)
  2. New tables (`CreateTable`)
  3. **Deferred FK `AddConstraint` ops** — emitted after all `CreateTable` ops so target tables exist
  4. Dropped tables (`DropTable`)
  5. Column changes on existing tables
- **FK `AddConstraint.to_ddl()`** emits `ALTER TABLE "table" ADD CONSTRAINT "name" FOREIGN KEY ("col") REFERENCES "schema"."target_table" ("target_col") ON DELETE ... ON UPDATE ...` wrapped in the same `DO $$ ... EXCEPTION` block as unique constraints.
- **Identifier-length validation** for FK names (same rule as 143).

Out of scope: cascading rename detection, ON DELETE SET DEFAULT, deferrable constraints.

## Acceptance criteria

- [ ] `ForeignKey` dataclass exists in [norm/model.py](norm/model.py) with `to`, `on_delete`, `on_update`, `name` fields
- [ ] `ForeignKey.to` accepts a `Field` proxy or a `"schema.table.column"` / `"table.column"` string
- [ ] Snapshot resolves `Field`-proxy targets to `(references_schema, references_table, references_column)` correctly
- [ ] Snapshot parses string FK targets correctly
- [ ] `FieldDef.fk` shortcut produces the same constraint dict as `TableMeta.foreign_keys` for equivalent declarations
- [ ] `diff_states` emits FK `AddConstraint` ops AFTER all `CreateTable` ops in the forward list
- [ ] FK `AddConstraint.to_ddl()` emits correct `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ... REFERENCES ... ON DELETE ... ON UPDATE ...` wrapped in `DO $$ ... EXCEPTION`
- [ ] FK auto-name `{table}_{column}_fkey`; > 63 chars raises pointing at `name=`
- [ ] Reverse op for FK `AddConstraint` is `DropConstraint(table, name)`
- [ ] Unit tests assert exact `to_ddl()` strings for FK `AddConstraint`
- [ ] Integration test: two tables with an FK between them, run `make` → migration emits `CreateTable` ops first, then FK `AddConstraint`; `apply` succeeds

## Blocked by

- [143 — Constraints + indexes with `concurrent=True` default and auto `atomic=False`](143-constraints-and-indexes-concurrent-defaults.md)
