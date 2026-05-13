# 14 — Schema metadata and DDL generation

Status: needs-triage
Type: HITL — API confirmation required before implementation

## What to build

Two layered capabilities:

1. **Schema metadata on models** — declare foreign keys, indexes, and constraints alongside the model. (Spec R15.)
2. **DDL generation** — a utility that emits `CREATE TABLE`, `CREATE INDEX`, and related DDL statements from the declared metadata. (Per the v1 scope decision: DDL is in scope.)

This does not perform DDL execution and does not handle migrations. It produces SQL strings; running them is the caller's responsibility.

### Schema metadata declarations

```python
from typing import Protocol, ClassVar, Annotated
from norm import col, fk, Index, Constraint, TableMeta, ForeignKey

class PostModel(Protocol):
    __meta__: ClassVar[TableMeta] = TableMeta(
        indexes=(
            Index(columns=("user_id", "created_at"), unique=False),
            Index(columns=("title",), partial="title IS NOT NULL"),
        ),
        constraints=(
            Constraint(kind="CHECK", expr="char_length(title) > 0",
                       name="chk_post_title_nonempty"),
        ),
    )

    id:       Annotated[int,        col(primary_key=True, db_default=True)]
    user_id:  Annotated[int,        col()]
    _fk_user: ClassVar[ForeignKey]  = fk(UserModel, "id", on_delete="CASCADE")
    title:    Annotated[str,        col(index=True)]
    body:     Annotated[str | None, col()]
```

### API options for the DDL entry point

**Option A — method on the table proxy**:

```python
sql = Users.create_table_ddl()
sql_indexes = Users.create_index_ddl()
```

Pros: discoverable from the proxy. Cons: mixes DDL into the query-building surface.

**Option B — standalone function**:

```python
from norm.ddl import create_table_ddl, create_index_ddl

sql = create_table_ddl(UserModel)             # works directly from the Protocol
sql_indexes = create_index_ddl(UserModel)
```

Pros: keeps the query-builder surface clean; doesn't require `table(Model)` first; one-import shape. Cons: another import path.

**Option C — both**: free function is the primary API; proxy method delegates to it.

### Usage example (once option chosen)

```python
ddl = create_table_ddl(UserModel)
# ddl == 'CREATE TABLE "accounts"."user" (
#           "id" SERIAL PRIMARY KEY,
#           "name" TEXT NOT NULL,
#           "email" TEXT NOT NULL UNIQUE,
#           "age" INTEGER,
#           CHECK (age >= 0)
#         )'
```

## Acceptance criteria

- [ ] User has confirmed the DDL entry-point API (A / B / C)
- [ ] `ForeignKey` / `fk()` declared as `ClassVar` on a model is read and rendered in DDL
- [ ] `Index` entries on `TableMeta.indexes` produce `CREATE INDEX` (or `CREATE UNIQUE INDEX`) statements, including partial-index `WHERE` clauses
- [ ] `Constraint` entries on `TableMeta.constraints` are rendered as table-level constraints (`CHECK`, `UNIQUE`, `EXCLUDE`)
- [ ] Field-level `col(index=True)` produces a single-column index
- [ ] Field-level `col(unique=True)` produces a column-level `UNIQUE` constraint
- [ ] Field-level `col(primary_key=True)` produces a primary key clause; combined with `db_default=True`, the SQL type uses an auto-incrementing form (e.g. `SERIAL` / `BIGSERIAL` — exact type-mapping choice documented on the issue)
- [ ] A Python → SQL type-mapping table is documented (int, str, str | None, etc.); custom mappings can be deferred to a future slice
- [ ] DDL generation does NOT execute against any database
- [ ] Unit tests assert exact DDL strings for: a simple model, a model with FK + index + check constraint, a model with partial index, a model with composite unique index
- [ ] No effect on the query-building surface (R15: schema metadata does not affect query building)

## Blocked by

- 01 — Tracer: end-to-end SELECT round-trip
