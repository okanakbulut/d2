# 145 — `View(query=...)` declaration + view ops + view diff strategy

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

The end-to-end view story. After this slice, a user can:

```python
class ActiveUsers(
    View,
    query=Users.select(Users.id, Users.email).where(Users.deleted_at.isnull()),
):
    id: PrimaryKey[int]
    email: Field[str]
```

…and `make` generates a `CreateView` op; `apply` creates the Postgres view; future query-time use of `ActiveUsers.select(ActiveUsers.email)` works.

### Scope

- **`NormMeta.__new__`** captures the `query=` class kwarg into `cls.__view_query__`. Cross-validates the annotated column list on the View body against `query.__columns__`: same names (in the same order) and same `python_type` for each. Raises `TypeError` at class-creation time on mismatch, with a message pointing at the offending column.
- **Operations**: `CreateView(name, definition, schema, replace=True)`, `DropView(name, schema, cascade=False)`. `apply` mutates `state.views`. `to_ddl` emits `CREATE [OR REPLACE] VIEW "schema"."name" AS <definition>` / `DROP VIEW IF EXISTS "schema"."name" [CASCADE]`.
- **`ViewState`** extension: `definition: str`, `columns: tuple[tuple[str, type], ...]`, `schema: str | None`.
- **Snapshot**: for each `View` subclass, store `cls.__view_query__.build()[0]` as `definition`; build `columns` from `__view_query__.__columns__`.
- **Diff strategy**:
  - Column list (names, types, order) unchanged but `definition` differs → emit `CreateView(replace=True)`
  - Column list changed → emit `DropView` + `CreateView` (because `CREATE OR REPLACE VIEW` rejects column-list reshapes)
  - View in target but not current → `CreateView`
  - View in current but not target → `DropView`
- **Codegen**: writes view ops with all fields by keyword.
- **Reverse ops**: for `CreateView` of a newly-created view → `DropView`; for `CreateView(replace=True)` replacing an existing definition → reverse `CreateView(replace=True)` with the previous definition.

Out of scope: materialized views, `WITH CHECK OPTION`, dependent-view cascade detection beyond what Postgres reports.

## Acceptance criteria

- [ ] `NormMeta.__new__` captures `query=` kwarg as `cls.__view_query__`
- [ ] Cross-validation: annotated columns on the View body must match `query.__columns__` by name (order preserved) and `python_type`; mismatch raises `TypeError` at class creation
- [ ] `ViewState` carries `definition`, `columns`, `schema`
- [ ] `CreateView`, `DropView` exist with correct `apply` and `to_ddl`
- [ ] Snapshot includes `View` subclasses; uses `query.build()[0]` for `definition`
- [ ] Diff emits `CreateView(replace=True)` when only definition changed
- [ ] Diff emits `DropView` + `CreateView` when column list changed
- [ ] Codegen writes view ops with all fields by keyword
- [ ] Reverse ops correctly invert view changes using `current` state
- [ ] Unit tests assert `to_ddl()` strings and `apply()` state mutations
- [ ] Integration test: declare a `View(query=...)`, run `make` + `apply`, query through the view returns correct rows; change the WHERE clause, `make` + `apply` again, view is replaced

## Blocked by

- [141 — Model snapshot + diff + codegen + CLI for tables](141-snapshot-diff-codegen-cli-for-tables.md)
