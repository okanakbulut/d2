# 05 — UPDATE and DELETE

Status: needs-triage
Type: AFK

## What to build

Support typed UPDATE statements and DELETE statements, both composable with `.where(...)` from the QueryBuilder layer. UPDATE assignments must use the typed `FieldProxy.set(...)` API — no string column names — and must support arithmetic expressions on the right-hand side (e.g. `col.set(col + 1)`) using the arithmetic operators from slice 02.

Partial update from a patch dict is **not** part of this slice — it ships separately as `15-patch-dict-update-helper.md`. In this slice, the caller writes one `col.set(value)` per assignment explicitly.

### Usage example

```python
# UPDATE with literal and column-arithmetic assignments
q = (
    Users
    .update(
        Users.age.set(Users.age + 1),         # col = col + 1
        Users.name.set("Veteran"),            # col = literal
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

- [ ] `FieldProxy.set(value)` returns an `Assignment`-like value object; `value` may be a literal (bound as parameter) or another `FieldProxy` / arithmetic expression (rendered inline)
- [ ] `_TableProxy.update(*assignments)` returns a `QueryBuilder` composable with `.where(...)`
- [ ] `_TableProxy.delete()` returns a `QueryBuilder` composable with `.where(...)`
- [ ] Both UPDATE and DELETE participate in the standard `(sql, params)` build path
- [ ] Arithmetic expressions in `set(...)` use the operators introduced in slice 02 — literal operands bind as parameters; column operands render inline
- [ ] Unit tests cover: literal SET, arithmetic SET, multi-column SET, UPDATE with WHERE, DELETE with WHERE
- [ ] End-to-end integration test against real PostgreSQL: seed rows, UPDATE a subset, DELETE another subset, verify the resulting state with SELECT

## Blocked by

- 02 — Comparison predicates, column aliasing, and ordering
- 04 — INSERT (single row and bulk)
