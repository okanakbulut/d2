# 01 — Tracer: end-to-end SELECT round-trip

Status: needs-triage
Type: AFK

## What to build

The thinnest possible cut through every layer of the library, so subsequent slices have a working spine to extend. After this slice, a user can:

1. Declare a `Protocol` model with typed `Annotated[T, col(...)]` fields.
2. Obtain a table proxy via `table(Model)` with typed `FieldProxy` attributes for each column.
3. Build an immutable `QueryBuilder` via `table_proxy.select(...)` / `.select_all()` and refine it with `.where(...)`.
4. Materialise the query into a `(sql, params)` pair via `.build()`, with positional placeholders and zero value interpolation.
5. Execute the query through an async connection and receive results hydrated into a `msgspec.Struct` subclass.

The dialect layer must be designed as a swappable seam — only the PostgreSQL implementation (`$N` placeholders) ships in this slice, but the interface must allow other dialects to plug in later (see [docs/typed-query-builder-spec.md](../docs/typed-query-builder-spec.md) Open Question #1).

Immutability is a correctness invariant from day one: mutating a `QueryBuilder` (or any other immutable object introduced here) must raise at runtime, not just be a convention.

### Usage example

```python
# myapp/accounts/models.py
from typing import Protocol, ClassVar, Annotated
from norm import col, TableMeta

class UserModel(Protocol):
    id:    Annotated[int, col(primary_key=True, db_default=True)]
    name:  Annotated[str, col(index=True)]
    email: Annotated[str, col(unique=True)]

# myapp/accounts/results.py
import msgspec

class UserResult(msgspec.Struct):
    id: int
    name: str
    email: str

# query site
from norm import table, AsyncConnection
from myapp.accounts.models import UserModel
from myapp.accounts.results import UserResult

Users = table(UserModel)

q = Users.select(Users.id, Users.name, Users.email).where(Users.id == 42)
sql, params = q.build()
# sql    == 'SELECT "id","name","email" FROM "accounts"."user" WHERE "id"=$1'
# params == (42,)

# execute end-to-end
conn = AsyncConnection(asyncpg_conn)
results: list[UserResult] = await conn.fetch(q, UserResult)
```

## Acceptance criteria

- [ ] `FieldDef` dataclass and `col(...)` factory exist; `Annotated[T, col(...)]` is parsed by the model layer
- [ ] `TableMeta` supports overriding `table` and `schema`; convention-based defaults apply otherwise (`UserModel` → `user`; `myapp.accounts.models` → schema `accounts`)
- [ ] `table(Model)` returns a class with named `FieldProxy` attributes for each declared column; second call with the same model returns the same class (cache)
- [ ] `@table` as model class decorator, it should return same table class with same name of model class
- [ ] A typo accessing `Users.nmae` raises `AttributeError` at access time (not at SQL execution time)
- [ ] `FieldProxy.__eq__` builds a typed predicate; literal values become bound parameters, never interpolated
- [ ] `_TableProxy.select(*proxies)` and `_TableProxy.select_all()` return a `QueryBuilder`
- [ ] `QueryBuilder.where(criterion)` returns a **new** `QueryBuilder`; the original is unchanged
- [ ] Setting an attribute on any `QueryBuilder` (or other immutable type introduced here) raises `AttributeError`
- [ ] `.build()` returns `(sql: str, params: tuple)`; positional placeholders are `$1`, `$2`, …; no literal values appear inside the SQL string
- [ ] The dialect rendering layer is structured so a non-Postgres dialect (e.g. `%s`) can be plugged in by swapping a single component; only the Postgres implementation ships in this slice
- [ ] `AsyncConnection.fetch(qb, ResultStruct)` returns `list[ResultStruct]` populated via `msgspec.convert`
- [ ] End-to-end integration test against a real PostgreSQL instance: define a model, insert a row via raw SQL fixture, query through the builder, get hydrated results
- [ ] Unit tests assert `(sql, params)` output without any database connection

## Blocked by

None — can start immediately.
