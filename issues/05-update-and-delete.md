# 05 — UPDATE and DELETE

Status: needs-triage
Type: AFK

## What to build

Support typed UPDATE statements and DELETE statements, both composable with `.where(...)` from the QueryBuilder layer. UPDATE assignments use `**kwargs` (bare attribute names as keys, values as literals or arithmetic expressions) — the same convention as `insert`. This means no `FieldProxy.set(...)` API; the right-hand side may be a literal (bound as parameter) or a `Field` / arithmetic expression (rendered inline).

Partial update from a patch dict is **not** part of this slice — it ships separately as `15-patch-dict-update-helper.md`. In this slice, the caller writes one kwarg per assignment explicitly.

> **Known limitation (shared with `insert`):** if a field declares a custom column name via `FieldDef(name=...)`, the kwarg key must match the Python attribute name, not the column name override. Fixing this uniformly across `insert` and `update` is deferred.

### Usage example

```python
# UPDATE with literal and column-arithmetic assignments
q = (
    Users
    .update(
        age=Users.age + 1,   # col = col + 1
        name="Veteran",      # col = literal
    )
    .where(Users.age >= 65)
)
sql, params = q.build()
# sql    == UPDATE "accounts"."user" SET "age"="age"+$1, "name"=$2 WHERE "age">=$3
# params == (1, "Veteran", 65)
await conn.execute(q)

# DELETE composable with where()
q = Users.delete().where(Users.id == 42)
await conn.execute(q)
```

## Acceptance criteria

- [ ] `Table.update(**assignments)` accepts bare attribute-name keys; values may be literals or `Field`/arithmetic expressions; returns a `QueryBuilder` composable with `.where(...)`
- [ ] `Table.delete()` returns a `QueryBuilder` composable with `.where(...)`
- [ ] Both UPDATE and DELETE participate in the standard `(sql, params)` build path
- [ ] Arithmetic expression values use the operators from slice 02 — literal operands bind as parameters; column operands render inline
- [ ] Unit tests cover: literal SET, arithmetic SET, multi-column SET, UPDATE with WHERE, DELETE with WHERE
- [ ] End-to-end integration test against real PostgreSQL: seed rows, UPDATE a subset, DELETE another subset, verify the resulting state with SELECT

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
- 04 — INSERT (single row and bulk)
