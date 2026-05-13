# Typed Query Builder — Design Specification

> A protocol-based, type-safe, async query builder that uses plain Python `Protocol` classes
> as model/table definitions and `pypika` as the SQL intermediate representation.
> `msgspec.Struct` is used exclusively for deserializing query results.

---

## Core Principles

1. **Model objects are protocols** — table/view definitions are pure `Protocol` classes. No base class, no dataclass, no msgspec dependency in the model layer.
2. **Immutable query builders** — every builder method returns a new builder instance. No mutation in place.
3. **No raw `Field` construction** — column references are always typed `FieldProxy` objects derived from model definitions. `pypika.Field(...)` is never called outside the internals.
4. **Parameterised queries** — `.build()` returns `(sql: str, params: tuple)`. Values are never interpolated into SQL strings. This is the only execution boundary.
5. **Async-only IO** — all database operations are `async def`. There is no sync execution path.
6. **msgspec for results only** — `msgspec.Struct` subclasses are the deserialization target for query results. They have no role in query building.
7. **Prefetch via JSON aggregation** — nested prefetch is compiled into a single SQL query using `json_agg` / `JSON_ARRAYAGG`, not N+1 or batched queries. No separate prefetch builder class.
8. **Subqueries are first-class** — a `QueryBuilder` can be wrapped as an inline view, producing a typed proxy with its own `FieldProxy` attributes usable in subsequent `.where()`, `.join()`, `.select()` calls.
9. **Table name and schema inferred by convention** — override with `__meta__` when needed.
10. **pypika as the IR** — SQL generation is delegated entirely to pypika. `.build()` calls `str(query)` once at the end.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  Model Layer  (pure Protocol classes)                            │
│                                                                  │
│  class UserModel(Protocol):                                      │
│      id:    Annotated[int, col(primary_key=True)]                │
│      name:  Annotated[str, col(index=True)]                      │
│      email: Annotated[str, col(unique=True)]                     │
│      age:   Annotated[int | None, col()]                         │
│                                                                  │
│  Table name  → inferred from class name  ("user")               │
│  Schema name → inferred from module name ("myapp.accounts")      │
│               or declared via __meta__ = TableMeta(...)          │
└──────────────────────────────┬───────────────────────────────────┘
                               │  table(UserModel)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Table Proxy  (generated at call time, immutable class)          │
│                                                                  │
│  Users.id       → FieldProxy[int]                                │
│  Users.name     → FieldProxy[str]                                │
│  Users.select() → QueryBuilder                                   │
└──────────────────────────────┬───────────────────────────────────┘
                               │  .where()  .join()  .prefetch()
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  QueryBuilder  (immutable — each method returns new instance)    │
│                                                                  │
│  .where(criterion)     → new QueryBuilder                        │
│  .join(...)            → new QueryBuilder                        │
│  .prefetch(...)        → new QueryBuilder  (JSON agg inline)     │
│  .as_view("alias")     → SubqueryProxy  (typed inline view)      │
│  .build()              → (sql: str, params: tuple)               │
└──────────────────────────────┬───────────────────────────────────┘
                               │  await conn.fetch(q, ResultStruct)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Hydration                                                       │
│                                                                  │
│  msgspec.convert(row_dict, UserResult)                           │
│  Nested prefetch rows are JSON-aggregated in the DB,             │
│  decoded by msgspec directly into nested Struct list fields.     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Model Layer

### `FieldDef[T]` — column declaration

`FieldDef[T]` carries column metadata. It is placed inside `Annotated[T, col(...)]` on protocol class bodies. The type parameter `T` is the Python type of the column value.

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass(frozen=True)
class FieldDef(Generic[T]):
    """
    Declared on Protocol model classes as column metadata.
    Never instantiated directly — use col() factory.
    """
    primary_key: bool       = False
    db_default:  bool       = False   # server-side default (SERIAL, NOW(), etc.)
    unique:      bool       = False
    index:       bool       = False
    db_column:   str | None = None    # override SQL column name

def col(
    *,
    primary_key: bool = False,
    db_default:  bool = False,
    unique:      bool = False,
    index:       bool = False,
    db_column:   str | None = None,
) -> FieldDef:
    return FieldDef(
        primary_key=primary_key,
        db_default=db_default,
        unique=unique,
        index=index,
        db_column=db_column,
    )
```

### `ForeignKey` — relationship metadata

```python
@dataclass(frozen=True)
class ForeignKey:
    """
    Declared as a ClassVar on a Protocol model to describe a FK relationship.
    Used for schema generation and documentation — not injected into query building.
    """
    references: type          # the referenced Protocol model class
    ref_column: str           # column name on the referenced table
    on_delete:  str = "NO ACTION"
    on_update:  str = "NO ACTION"

def fk(
    references: type,
    ref_column: str = "id",
    *,
    on_delete: str = "NO ACTION",
    on_update: str = "NO ACTION",
) -> ForeignKey:
    return ForeignKey(references, ref_column, on_delete, on_update)
```

### `Index` and `Constraint` — schema-level declarations

```python
@dataclass(frozen=True)
class Index:
    columns:  tuple[str, ...]
    unique:   bool       = False
    partial:  str | None = None   # SQL WHERE clause for partial index
    name:     str | None = None   # override index name

@dataclass(frozen=True)
class Constraint:
    kind:  str            # "CHECK", "UNIQUE", "EXCLUDE"
    expr:  str            # raw SQL expression
    name:  str | None = None
```

### `TableMeta` — optional class-level overrides

```python
@dataclass(frozen=True)
class TableMeta:
    table:       str | None                = None
    schema:      str | None                = None
    indexes:     tuple[Index, ...]         = ()
    constraints: tuple[Constraint, ...]    = ()
```

### Naming convention

Table names are derived from the Protocol class name by stripping a trailing `Model` suffix and converting `CamelCase` to `snake_case`:

| Class name            | Inferred table |
|-----------------------|----------------|
| `UserModel`           | `user`         |
| `BlogPostModel`       | `blog_post`    |
| `OrderLineItemModel`  | `order_line_item` |

Schema is inferred from the module path: `myapp.accounts.models` → schema `accounts`. If the module path has no `models` segment, no schema qualifier is applied.

Both are overridden by declaring `__meta__ = TableMeta(table="...", schema="...")`.

---

### Concrete model definitions

```python
# myapp/accounts/models.py
# Inferred schema: "accounts"

from typing import Protocol, ClassVar, Annotated
from qb import FieldDef, col, fk, ForeignKey, TableMeta, Index, Constraint

class UserModel(Protocol):
    __meta__: ClassVar[TableMeta] = TableMeta(
        indexes=(
            Index(columns=("name", "email"), unique=True),
            Index(columns=("age",), partial="age IS NOT NULL"),
        ),
        constraints=(
            Constraint(kind="CHECK", expr="age >= 0", name="chk_user_age_positive"),
        ),
    )

    id:         Annotated[int,        col(primary_key=True, db_default=True)]
    name:       Annotated[str,        col(index=True)]
    email:      Annotated[str,        col(unique=True)]
    age:        Annotated[int | None, col()]
    created_at: Annotated[str,        col(db_default=True)]


class PostModel(Protocol):
    id:       Annotated[int,        col(primary_key=True, db_default=True)]
    user_id:  Annotated[int,        col()]
    _fk_user: ClassVar[ForeignKey]  = fk(UserModel, "id", on_delete="CASCADE")
    title:    Annotated[str,        col(index=True)]
    body:     Annotated[str | None, col()]


class CommentModel(Protocol):
    id:       Annotated[int,  col(primary_key=True, db_default=True)]
    post_id:  Annotated[int,  col()]
    _fk_post: ClassVar[ForeignKey] = fk(PostModel, "id", on_delete="CASCADE")
    user_id:  Annotated[int,  col()]
    _fk_user: ClassVar[ForeignKey] = fk(UserModel, "id", on_delete="CASCADE")
    body:     Annotated[str,  col()]
```

### View models follow the same protocol

```python
class ActiveUserViewModel(Protocol):
    __meta__: ClassVar[TableMeta] = TableMeta(table="active_users_view")

    id:    Annotated[int, col(primary_key=True)]
    name:  Annotated[str, col()]
    email: Annotated[str, col()]
```

---

## `FieldProxy[T]` — Typed Column Reference

`FieldProxy` is the object exposed as a class attribute on a table proxy. It wraps a pypika `Term` internally. All comparisons and functions produce pypika `Criterion` objects or new `FieldProxy` instances. Literal values passed to comparisons are wrapped as bound parameters — never interpolated.

```python
from pypika.terms import ValueWrapper, Criterion, Term
from pypika import functions as fn
from typing import Generic, TypeVar, Any

T = TypeVar("T")

class FieldProxy(Generic[T]):
    """
    Typed handle to a single column or expression.
    Exposes comparison operators, aggregations, window functions, and aliasing.
    All literal values become bound parameters via _param().
    """
    def __init__(self, term: Term, py_type: type[T], col_name: str,
                 alias: str | None = None):
        self._term     = term
        self._col_name = col_name
        self._alias    = alias
        self.py_type   = py_type

    # --- comparisons → Criterion ---
    def __eq__(self, val: T | "FieldProxy") -> Criterion:
        return self._term == (val._term if isinstance(val, FieldProxy) else _param(val))
    def __ne__(self, val) -> Criterion:
        return self._term != (val._term if isinstance(val, FieldProxy) else _param(val))
    def __gt__(self, val) -> Criterion:
        return self._term >  (val._term if isinstance(val, FieldProxy) else _param(val))
    def __lt__(self, val) -> Criterion:
        return self._term <  (val._term if isinstance(val, FieldProxy) else _param(val))
    def __ge__(self, val) -> Criterion:
        return self._term >= (val._term if isinstance(val, FieldProxy) else _param(val))
    def __le__(self, val) -> Criterion:
        return self._term <= (val._term if isinstance(val, FieldProxy) else _param(val))

    # --- predicates ---
    def like(self, pat: str)         -> Criterion: return self._term.like(_param(pat))
    def ilike(self, pat: str)        -> Criterion: return self._term.ilike(_param(pat))
    def isin(self, vals: list[T])    -> Criterion: return self._term.isin([_param(v) for v in vals])
    def notin(self, vals: list[T])   -> Criterion: return self._term.notin([_param(v) for v in vals])
    def isnull(self)                 -> Criterion: return self._term.isnull()
    def isnotnull(self)              -> Criterion: return self._term.isnotnull()
    def between(self, lo: T, hi: T)  -> Criterion:
        return self._term.between(_param(lo), _param(hi))

    # --- aggregations → new FieldProxy ---
    def count(self, distinct: bool = False) -> "FieldProxy[int]":
        expr = fn.Count(self._term).distinct() if distinct else fn.Count(self._term)
        return self._wrap(expr, int)

    def sum(self)  -> "FieldProxy[T]":     return self._wrap(fn.Sum(self._term),  self.py_type)
    def avg(self)  -> "FieldProxy[float]": return self._wrap(fn.Avg(self._term),  float)
    def min(self)  -> "FieldProxy[T]":     return self._wrap(fn.Min(self._term),  self.py_type)
    def max(self)  -> "FieldProxy[T]":     return self._wrap(fn.Max(self._term),  self.py_type)

    def coalesce(self, default: T) -> "FieldProxy[T]":
        return self._wrap(fn.Coalesce(self._term, _param(default)), self.py_type)

    def cast(self, sql_type: str) -> "FieldProxy":
        from pypika.terms import Cast
        return self._wrap(Cast(self._term, sql_type), Any)

    # --- window functions ---
    def over(self, *partition_by: "FieldProxy") -> "WindowSpec":
        return WindowSpec(self._term, partition_by=partition_by)

    # --- aliasing ---
    def as_(self, alias: str) -> "FieldProxy[T]":
        return FieldProxy(self._term.as_(alias), self.py_type, self._col_name, alias=alias)

    # --- UPDATE assignment ---
    def set(self, val: "T | FieldProxy[T]") -> "Assignment":
        rhs = val._term if isinstance(val, FieldProxy) else _param(val)
        return Assignment(self._term, rhs)

    # --- arithmetic (for SET col = col + 1) ---
    def __add__(self, val) -> "FieldProxy[T]":
        return self._wrap(self._term + _param(val), self.py_type)
    def __sub__(self, val) -> "FieldProxy[T]":
        return self._wrap(self._term - _param(val), self.py_type)
    def __mul__(self, val) -> "FieldProxy[T]":
        return self._wrap(self._term * _param(val), self.py_type)
    def __truediv__(self, val) -> "FieldProxy[T]":
        return self._wrap(self._term / _param(val), self.py_type)

    def _wrap(self, term: Term, py_type: type) -> "FieldProxy":
        return FieldProxy(term, py_type, self._col_name, self._alias)

    def __repr__(self) -> str:
        return f"FieldProxy({self._col_name!r}: {getattr(self.py_type, '__name__', str(self.py_type))})"


class WindowSpec:
    """Intermediate for building window function expressions."""
    def __init__(self, term: Term, partition_by: tuple["FieldProxy", ...] = ()):
        self._term          = term
        self._partition_by  = partition_by
        self._order_proxies: list[FieldProxy] = []

    def order_by(self, *proxies: FieldProxy) -> "WindowSpec":
        ws              = WindowSpec(self._term, self._partition_by)
        ws._order_proxies = list(proxies)
        return ws

    def as_(self, alias: str) -> FieldProxy:
        from pypika.analytics import Window
        window = (
            Window(self._term)
            .over(*[p._term for p in self._partition_by])
            .orderby(*[p._term for p in self._order_proxies])
        )
        return FieldProxy(window.as_(alias), Any, alias, alias=alias)


@dataclass(frozen=True)
class Assignment:
    field: Term
    value: Term


def _param(val) -> ValueWrapper:
    """Wrap a Python literal as a pypika bound-parameter placeholder."""
    return ValueWrapper(val)
```

---

## `table()` — Table Proxy Factory

`table(Model)` returns a generated class whose class attributes are `FieldProxy` instances. Results are cached so the same model always produces the same class.

```python
import re
from typing import get_type_hints, get_origin, get_args, Annotated
from pypika import Table as PTable, Schema

_TABLE_CACHE: dict[type, type] = {}


def _model_to_table_name(cls: type) -> str:
    name = re.sub(r"Model$", "", cls.__name__)
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _model_to_schema_name(cls: type) -> str | None:
    parts = cls.__module__.split(".")
    if "models" in parts:
        idx = parts.index("models")
        if idx > 0:
            return parts[idx - 1]
    return None


def _resolve_ptable(cls: type, alias: str | None = None) -> PTable:
    meta: TableMeta | None = getattr(cls, "__meta__", None)
    table_name  = (meta.table  if meta and meta.table  else None) or _model_to_table_name(cls)
    schema_name = (meta.schema if meta and meta.schema else None) or _model_to_schema_name(cls)
    base = Schema(schema_name).__getattr__(table_name) if schema_name else PTable(table_name)
    return base.as_(alias) if alias else base


def _extract_fields(cls: type) -> dict[str, tuple[type, FieldDef]]:
    hints = get_type_hints(cls, include_extras=True)
    out   = {}
    for name, hint in hints.items():
        if name.startswith("_"):
            continue
        if get_origin(hint) is Annotated:
            py_type, *meta = get_args(hint)
            fd = next((m for m in meta if isinstance(m, FieldDef)), FieldDef())
        else:
            py_type, fd = hint, FieldDef()
        out[name] = (py_type, fd)
    return out


class _ProxyMeta(type):
    def __new__(mcs, name, bases, ns, *, _model=None, _ptable=None, _fields=None, **kw):
        cls = super().__new__(mcs, name, bases, ns, **kw)
        if _model is None:
            return cls
        for attr_name, (py_type, fd) in _fields.items():
            sql_col = fd.db_column or attr_name
            setattr(cls, attr_name, FieldProxy(_ptable[sql_col], py_type, sql_col))
        cls._model  = _model
        cls._ptable = _ptable
        cls._fields = _fields
        return cls


def table(model: type, *, alias: str | None = None) -> type:
    """
    Return a table proxy class for the given Protocol model.
    Cached by model class. Pass alias= for self-joins and CTE references.
    """
    if alias:
        # Aliased proxies bypass the cache — each alias is a distinct class
        ptable = _resolve_ptable(model, alias=alias)
        fields = _extract_fields(model)
        return _ProxyMeta(
            f"{model.__name__}Proxy_{alias}",
            (_TableProxy,),
            {},
            _model=model,
            _ptable=ptable,
            _fields=fields,
        )

    if model not in _TABLE_CACHE:
        ptable = _resolve_ptable(model)
        fields = _extract_fields(model)
        _TABLE_CACHE[model] = _ProxyMeta(
            f"{model.__name__}Proxy",
            (_TableProxy,),
            {},
            _model=model,
            _ptable=ptable,
            _fields=fields,
        )

    return _TABLE_CACHE[model]
```

---

## `_TableProxy` — Query Entry Points

All query-initiating class methods live here. They construct the initial pypika query object and hand it off to `QueryBuilder`.

```python
import pypika
import msgspec
from typing import TypeVar

S = TypeVar("S", bound=msgspec.Struct)


class _TableProxy:

    # SELECT
    @classmethod
    def select(cls, *proxies: FieldProxy) -> "QueryBuilder":
        q = pypika.Query.from_(cls._ptable).select(*[p._term for p in proxies])
        return QueryBuilder(cls, q)

    @classmethod
    def select_all(cls) -> "QueryBuilder":
        q = pypika.Query.from_(cls._ptable).select(pypika.Star())
        return QueryBuilder(cls, q)

    # INSERT
    @classmethod
    def insert(cls, data: dict, *, exclude_defaults: bool = True) -> "QueryBuilder":
        if exclude_defaults:
            skip = {k for k, (_, fd) in cls._fields.items() if fd.db_default or fd.primary_key}
            data = {k: v for k, v in data.items() if k not in skip}
        cols   = list(data.keys())
        params = [_param(v) for v in data.values()]
        q      = pypika.Query.into(cls._ptable).columns(*cols).insert(*params)
        return QueryBuilder(cls, q)

    @classmethod
    def insert_many(cls, rows: list[dict], *, exclude_defaults: bool = True) -> "QueryBuilder":
        if not rows:
            raise ValueError("insert_many requires at least one row")
        if exclude_defaults:
            skip = {k for k, (_, fd) in cls._fields.items() if fd.db_default or fd.primary_key}
            rows = [{k: v for k, v in r.items() if k not in skip} for r in rows]
        cols = list(rows[0].keys())
        q    = pypika.Query.into(cls._ptable).columns(*cols)
        for row in rows:
            q = q.insert(*[_param(v) for v in row.values()])
        return QueryBuilder(cls, q)

    # UPDATE
    @classmethod
    def update(cls, *assignments: Assignment) -> "QueryBuilder":
        q = pypika.Query.update(cls._ptable)
        for a in assignments:
            q = q.set(a.field, a.value)
        return QueryBuilder(cls, q)

    # DELETE
    @classmethod
    def delete(cls) -> "QueryBuilder":
        q = pypika.Query.from_(cls._ptable).delete()
        return QueryBuilder(cls, q)

    # Hydration
    @classmethod
    def hydrate(cls, rows: list[tuple], description: list, target: type[S]) -> list[S]:
        col_names = [d[0] for d in description]
        return [msgspec.convert(dict(zip(col_names, row)), target) for row in rows]
```

---

## `QueryBuilder` — Immutable Fluent Builder

Every method returns a **new** instance. Mutation is forbidden via `__setattr__`.

```python
from pypika import Order, Criterion

class QueryBuilder:
    """
    Immutable SQL query builder.
    .build() → (sql: str, params: tuple)
    """
    __slots__ = ("_proxy_cls", "_query", "_prefetches", "_ctes")

    def __init__(self, proxy_cls, query, prefetches=(), ctes=()):
        object.__setattr__(self, "_proxy_cls",  proxy_cls)
        object.__setattr__(self, "_query",      query)
        object.__setattr__(self, "_prefetches", prefetches)
        object.__setattr__(self, "_ctes",       ctes)

    def __setattr__(self, *_):
        raise AttributeError("QueryBuilder is immutable")

    def _replace(self, **kw) -> "QueryBuilder":
        return QueryBuilder(
            kw.get("_proxy_cls",  self._proxy_cls),
            kw.get("_query",      self._query),
            kw.get("_prefetches", self._prefetches),
            kw.get("_ctes",       self._ctes),
        )

    # --- filtering ---
    def where(self, criterion: Criterion)  -> "QueryBuilder":
        return self._replace(_query=self._query.where(criterion))

    def having(self, criterion: Criterion) -> "QueryBuilder":
        return self._replace(_query=self._query.having(criterion))

    # --- joins (other is a table proxy or SubqueryProxy) ---
    def join(self, other, on: Criterion)       -> "QueryBuilder":
        return self._replace(_query=self._query.join(other._ptable).on(on))

    def left_join(self, other, on: Criterion)  -> "QueryBuilder":
        return self._replace(_query=self._query.left_join(other._ptable).on(on))

    def right_join(self, other, on: Criterion) -> "QueryBuilder":
        return self._replace(_query=self._query.right_join(other._ptable).on(on))

    def cross_join(self, other)                -> "QueryBuilder":
        return self._replace(_query=self._query.cross_join(other._ptable))

    # --- grouping / ordering / pagination ---
    def group_by(self, *proxies: FieldProxy)   -> "QueryBuilder":
        return self._replace(_query=self._query.groupby(*[p._term for p in proxies]))

    def order_by(self, *proxies: FieldProxy, desc: bool = False) -> "QueryBuilder":
        order = Order.desc if desc else Order.asc
        return self._replace(_query=self._query.orderby(*[p._term for p in proxies], order=order))

    def limit(self, n: int)  -> "QueryBuilder":
        return self._replace(_query=self._query.limit(n))

    def offset(self, n: int) -> "QueryBuilder":
        return self._replace(_query=self._query.offset(n))

    def distinct(self)       -> "QueryBuilder":
        return self._replace(_query=self._query.distinct())

    # --- set operations ---
    def union(self, other: "QueryBuilder")     -> "QueryBuilder":
        return self._replace(_query=self._query.union(other._query))

    def union_all(self, other: "QueryBuilder") -> "QueryBuilder":
        return self._replace(_query=self._query.union_all(other._query))

    def intersect(self, other: "QueryBuilder") -> "QueryBuilder":
        return self._replace(_query=self._query.intersect(other._query))

    def except_(self, other: "QueryBuilder")   -> "QueryBuilder":
        return self._replace(_query=self._query.except_of(other._query))

    # --- CTEs ---
    def with_cte(self, name: str, cte_qb: "QueryBuilder") -> "QueryBuilder":
        return self._replace(_ctes=self._ctes + ((name, cte_qb._query, False),))

    def with_recursive_cte(self, name: str,
                            anchor: "QueryBuilder",
                            recursive: "QueryBuilder") -> "QueryBuilder":
        combined = anchor._query.union_all(recursive._query)
        return self._replace(_ctes=self._ctes + ((name, combined, True),))

    # --- inline view / subquery ---
    def as_view(self, alias: str) -> "SubqueryProxy":
        """
        Wrap this QueryBuilder as a named inline view.
        Returns a SubqueryProxy whose FieldProxy attributes can be used
        in any subsequent .where(), .join(), or .select() call.
        """
        return SubqueryProxy(alias, self._query, self._proxy_cls._fields)

    def as_scalar(self):
        """
        Return this query as a scalar subquery term.
        Used in WHERE comparisons: .where(Users.age > sub_qb.as_scalar())
        """
        return self._query

    # --- prefetch via JSON aggregation ---
    def prefetch(
        self,
        child_proxy: type,
        *,
        fk:          FieldProxy,
        pk:          FieldProxy,
        result_col:  str,
        child_select: "QueryBuilder | None" = None,
    ) -> "QueryBuilder":
        """
        Append a correlated JSON-aggregation subquery for child rows.
        Produces no additional SQL queries at execution time — the aggregation
        runs in the database and the JSON column is decoded by msgspec.

        child_select: optional pre-built QueryBuilder for filtering/shaping
                      child rows (including further nested .prefetch() calls).
                      Defaults to child_proxy.select_all().
        """
        inner_qb = child_select or child_proxy.select_all()
        # Correlate child FK to parent PK
        correlated = inner_qb.where(fk == pk)

        from pypika import functions as fn
        agg_term   = fn.Function("json_agg", pypika.Star()).as_(result_col)
        inner_sql  = correlated._query

        new_prefetches = self._prefetches + ((agg_term, inner_sql, result_col),)
        return self._replace(_prefetches=new_prefetches)

    # --- build ---
    def build(self) -> tuple[str, tuple]:
        """
        Materialise the query into (sql, params).
        SQL uses positional placeholders ($1, $2, ...).
        Values are never interpolated.
        """
        q = self._query
        for cte_name, cte_q, _ in self._ctes:
            q = q.with_(cte_q, cte_name)

        dialect = ParameterisedDialect()
        sql, params = dialect.render(q)
        return sql, params
```

---

## `SubqueryProxy` — Typed Inline View

`SubqueryProxy` is produced by `.as_view("alias")`. It exposes the same `FieldProxy` attributes as the originating table proxy, scoped to the alias, so outer queries can reference subquery output columns without any string literals.

```python
class SubqueryProxy:
    """
    A named inline view wrapping a QueryBuilder.
    Its FieldProxy attributes let the outer query reference subquery
    output columns in .where(), .join(), and .select() — fully typed.
    """
    __slots__ = ()   # dynamic attrs set via object.__setattr__

    def __init__(self, alias: str, inner_query, fields: dict[str, tuple[type, FieldDef]]):
        object.__setattr__(self, "_alias",  alias)
        object.__setattr__(self, "_inner",  inner_query)
        object.__setattr__(self, "_ptable", PTable(alias))

        alias_table = PTable(alias)
        for col_name, (py_type, _) in fields.items():
            object.__setattr__(self,
                col_name,
                FieldProxy(alias_table[col_name], py_type, col_name))

    def __setattr__(self, *_):
        raise AttributeError("SubqueryProxy is immutable")
```

---

## Parameter Extraction

pypika does not natively emit `$N` placeholders. The `ParameterisedDialect` rendering layer intercepts `ValueWrapper` nodes, collects their values in order, and replaces them with positional markers.

```python
class ParameterisedDialect:
    """
    Renders a pypika query tree to (parameterised_sql, params_tuple).
    Positional placeholders: $1, $2, ... (PostgreSQL style).
    Swap to %s for psycopg2/mysql.
    """
    def render(self, query) -> tuple[str, tuple]:
        self._params: list = []
        self._counter      = 0
        sql = self._render_query(query)
        return sql, tuple(self._params)

    def _next_placeholder(self, val) -> str:
        self._params.append(val)
        self._counter += 1
        return f"${self._counter}"

    def _render_query(self, query) -> str:
        # Walk the pypika query tree via its .get_sql() with a custom
        # ValueWrapper override that calls _next_placeholder().
        # Implementation: subclass pypika's PostgreSQLQuery and override
        # ValueWrapper.get_sql in the render scope.
        ...
```

> The precise implementation monkeypatches `ValueWrapper.get_sql` within the render scope or uses a pypika `PostgreSQLQuery` dialect subclass. It is ~30 lines, fully isolated inside `ParameterisedDialect.render()`, and invisible to callers.

---

## Async Execution Layer

All IO is `async def`. `QueryBuilder` never touches a connection — it only produces `(sql, params)`.

```python
import msgspec
from typing import Any, TypeVar

S = TypeVar("S", bound=msgspec.Struct)


class AsyncConnection:
    """
    Thin async wrapper over any DB driver (asyncpg, psycopg3, aiosqlite).
    Accepts QueryBuilder instances directly.
    """
    def __init__(self, conn):
        self._conn = conn

    async def fetch(self, qb: QueryBuilder, result_type: type[S]) -> list[S]:
        sql, params = qb.build()
        rows        = await self._conn.fetch(sql, *params)
        return [msgspec.convert(dict(row), result_type) for row in rows]

    async def fetch_one(self, qb: QueryBuilder, result_type: type[S]) -> S | None:
        sql, params = qb.build()
        row         = await self._conn.fetchrow(sql, *params)
        return msgspec.convert(dict(row), result_type) if row else None

    async def fetch_val(self, qb: QueryBuilder) -> Any:
        sql, params = qb.build()
        return await self._conn.fetchval(sql, *params)

    async def execute(self, qb: QueryBuilder) -> str:
        sql, params = qb.build()
        return await self._conn.execute(sql, *params)

    async def execute_many(self, qb: QueryBuilder) -> None:
        sql, params = qb.build()
        await self._conn.executemany(sql, params)

    async def transaction(self):
        return self._conn.transaction()   # used as async context manager
```

---

## Prefetch via JSON Aggregation

Nested prefetch emits **one SQL query** using correlated `json_agg` subqueries. The depth of nesting is unbounded — each `.prefetch()` call inlines another level.

```python
# Result structs — msgspec.Struct only, for deserialization
class CommentResult(msgspec.Struct):
    id:   int
    body: str

class PostResult(msgspec.Struct):
    id:       int
    title:    str
    comments: list[CommentResult]   # populated from JSON column

class UserResult(msgspec.Struct):
    id:    int
    name:  str
    email: str
    posts: list[PostResult]         # populated from JSON column


# Single query with two levels of nesting
q = (
    Users
    .select(Users.id, Users.name, Users.email)
    .prefetch(
        Posts,
        fk=Posts.user_id,
        pk=Users.id,
        result_col="posts",
        child_select=(
            Posts
            .select(Posts.id, Posts.title)
            .prefetch(
                Comments,
                fk=Comments.post_id,
                pk=Posts.id,
                result_col="comments",
                child_select=Comments.select(Comments.id, Comments.body),
            )
        ),
    )
    .where(Users.age >= 18)
    .order_by(Users.name)
)

# Emitted SQL (PostgreSQL):
# SELECT
#   "accounts"."user".id,
#   "accounts"."user".name,
#   "accounts"."user".email,
#   (
#     SELECT json_agg(*)
#     FROM (
#       SELECT posts.id, posts.title,
#              (
#                SELECT json_agg(*)
#                FROM (
#                  SELECT comments.id, comments.body
#                  FROM comments
#                  WHERE comments.post_id = posts.id
#                )
#              ) AS comments
#       FROM posts
#       WHERE posts.user_id = "accounts"."user".id
#     )
#   ) AS posts
# FROM "accounts"."user"
# WHERE "accounts"."user".age >= $1
# ORDER BY "accounts"."user".name ASC
#
# params: (18,)

results: list[UserResult] = await conn.fetch(q, UserResult)
# results[0].posts[0].comments[0].body  ← fully nested, one round-trip
```

`msgspec.convert` decodes the `json_agg` JSON value into the nested `list[PostResult]` → `list[CommentResult]` tree automatically, because the target struct's field types describe the exact nesting shape.

---

## Aliasing

### Column aliasing

```python
q = Users.select(
    Users.name.as_("author"),
    Posts.title.as_("post_title"),
).join(Posts, on=Users.id == Posts.user_id)
```

### Table aliasing (self-joins)

```python
Mgr = table(EmployeeModel, alias="mgr")
Rep = table(EmployeeModel, alias="rep")

q = (
    Mgr
    .select(Mgr.name.as_("manager_name"), Rep.name.as_("report_name"))
    .join(Rep, on=Mgr.id == Rep.manager_id)
    .build()
)
# → SELECT mgr.name AS manager_name, rep.name AS report_name
#   FROM employees mgr JOIN employees rep ON mgr.id = rep.manager_id
```

### Subquery as inline view

```python
revenue_by_user = (
    Orders
    .select(Orders.user_id, Orders.amount.sum().as_("total"))
    .group_by(Orders.user_id)
    .as_view("rev")                        # SubqueryProxy: .user_id, .total
)

q = (
    Users
    .select(Users.name, revenue_by_user.total)
    .join(revenue_by_user, on=Users.id == revenue_by_user.user_id)
    .where(revenue_by_user.total > 1000)   # typed column reference on subquery
    .build()
)
# → SELECT users.name, rev.total
#   FROM users
#   JOIN (SELECT user_id, SUM(amount) AS total FROM orders GROUP BY user_id) rev
#     ON users.id = rev.user_id
#   WHERE rev.total > $1
# params: (1000,)
```

### CTE aliasing

```python
recent_qb = Posts.select_all().where(Posts.created_at >= "2024-01-01")
RecentPosts = recent_qb.as_view("recent_posts")   # SubqueryProxy

q = (
    Users
    .select(Users.name, RecentPosts.title)
    .with_cte("recent_posts", recent_qb)
    .join(RecentPosts, on=Users.id == RecentPosts.user_id)
    .build()
)
# → WITH recent_posts AS (SELECT * FROM posts WHERE created_at >= $1)
#   SELECT users.name, recent_posts.title
#   FROM users JOIN recent_posts ON users.id = recent_posts.user_id
# params: ("2024-01-01",)
```

---

## Recursive CTEs

```python
Emp    = table(EmployeeModel)
EmpCTE = table(EmployeeModel, alias="org_cte")  # self-reference inside the CTE

anchor    = (Emp
             .select(Emp.id, Emp.name, Emp.manager_id)
             .where(Emp.manager_id.isnull()))

recursive = (Emp
             .select(Emp.id, Emp.name, Emp.manager_id)
             .join(EmpCTE, on=Emp.manager_id == EmpCTE.id))

q = (
    Emp
    .select_all()
    .with_recursive_cte("org_cte", anchor=anchor, recursive=recursive)
    .build()
)
# → WITH RECURSIVE org_cte AS (
#       SELECT id, name, manager_id FROM employees WHERE manager_id IS NULL
#       UNION ALL
#       SELECT e.id, e.name, e.manager_id
#       FROM employees e JOIN org_cte ON e.manager_id = org_cte.id
#   )
#   SELECT * FROM employees
```

---

## Functions and Aggregations

```python
# COUNT DISTINCT, AVG, MAX, COALESCE
q = (
    Users
    .select(
        Users.id.count(distinct=True).as_("unique_users"),
        Users.age.avg().as_("avg_age"),
        Users.age.max().as_("oldest"),
        Users.age.coalesce(0).as_("age_safe"),
    )
    .group_by(Users.name)
    .having(Users.id.count() > 5)
    .build()
)

# Window function
row_num = (
    Users.id
    .over(Users.name)
    .order_by(Users.created_at)
    .as_("row_num")
)
q = Users.select(Users.name, row_num).build()

# CAST
q = Users.select(Users.age.cast("float").as_("age_f")).build()

# Arithmetic in UPDATE
q = (
    Users
    .update(
        Users.age.set(Users.age + 1),
        Users.name.set("Veteran"),
    )
    .where(Users.age >= 65)
    .build()
)
# params: (1, "Veteran", 65)
```

---

## Set Operations

```python
adults = Users.select_all().where(Users.age >= 18)
minors = Users.select_all().where(Users.age <  18)

q = adults.union(minors).order_by(Users.name).build()
q = adults.union_all(minors).build()

active     = Users.select_all().where(Users.email.isnotnull())
subscribed = Users.select_all().where(Users.subscribed == True)
q = active.intersect(subscribed).build()

all_users = Users.select_all()
banned    = Users.select_all().where(Users.banned == True)
q = all_users.except_(banned).build()
```

---

## INSERT / UPDATE / DELETE

```python
# Single insert
q = Users.insert({"name": "Alice", "email": "alice@example.com", "age": 30})
sql, params = q.build()
# → INSERT INTO "accounts"."user" (name, email, age) VALUES ($1, $2, $3)
# params: ("Alice", "alice@example.com", 30)

# Bulk insert
q = Users.insert_many([
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob",   "email": "bob@example.com",   "age": 25},
])

# Upsert
q = (
    Users
    .insert({"name": "Alice", "email": "alice@example.com"})
    .on_conflict(Users.email)
    .do_update(Users.name)
    .build()
)

# Partial update from a patch dict
patch = {"age": 33}   # e.g. from msgspec.to_builtins(UserPatch(age=33))
q = (
    Users
    .update(*[getattr(Users, col).set(val) for col, val in patch.items()])
    .where(Users.id == 42)
    .build()
)
# → UPDATE "accounts"."user" SET age=$1 WHERE id=$2
# params: (33, 42)

# Delete
q = Users.delete().where(Users.id == 42).build()
# → DELETE FROM "accounts"."user" WHERE id=$1
# params: (42,)
```

---

## Module Layout

```
myapp/
├── accounts/
│   ├── models.py       ← Protocol model definitions (UserModel, etc.)
│   └── results.py      ← msgspec.Struct result types (UserResult, etc.)
├── blog/
│   ├── models.py       ← PostModel, CommentModel
│   └── results.py      ← PostResult, CommentResult
└── db/
    ├── field.py        ← FieldDef, col(), FieldProxy, WindowSpec, Assignment, _param()
    ├── constraints.py  ← ForeignKey, fk(), Index, Constraint, TableMeta
    ├── proxy.py        ← table(), _TableProxy, _ProxyMeta, SubqueryProxy
    ├── builder.py      ← QueryBuilder
    ├── params.py       ← ParameterisedDialect
    └── conn.py         ← AsyncConnection
```

Application code only ever imports from `models.py` and `db/proxy.py`:

```python
from myapp.accounts.models import UserModel
from myapp.blog.models     import PostModel, CommentModel
from myapp.db.proxy        import table

Users    = table(UserModel)
Posts    = table(PostModel)
Comments = table(CommentModel)
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Models are `Protocol` classes | Zero dependency in the model layer. No inheritance. Structurally verified at `table()` time. Existing classes that happen to match the shape work automatically. |
| `FieldDef` in `Annotated` | Colocated with the type. `get_type_hints(include_extras=True)` reads both in one pass. Protocol body stays declarative and readable. |
| Table/schema inferred by convention | No boilerplate for standard layouts. `TableMeta` override is only needed for legacy names or multi-schema setups. |
| `QueryBuilder` is immutable | Safe to branch, compose, and store partial queries. No action-at-a-distance bugs from shared mutable state. |
| No `pypika.Field(...)` at call sites | All column references go through `FieldProxy`. Typos are caught at attribute access, not at execution time. |
| `(sql, params)` from `.build()` | Hard boundary between structure and values. SQL injection is architecturally impossible — values never reach the SQL string. |
| Async-only IO | No sync path to accidentally block the event loop. `QueryBuilder` is IO-free; `AsyncConnection` is the only place IO lives. |
| Prefetch via `json_agg` | One round-trip regardless of nesting depth. No N+1. No Cartesian blowup from JOIN-based approaches. `msgspec.convert` decodes JSON columns directly into nested Struct trees. |
| `SubqueryProxy` from `.as_view()` | Subquery output columns are typed. Outer query predicates and join conditions on subquery results are fully typed — no string column names. Used uniformly for subqueries and CTEs. |
| Single `QueryBuilder` type | No separate `InsertBuilder`, `CTEBuilder`, `PrefetchQueryBuilder`. One type, one API surface. Prefetch, CTEs, and set operations are methods on the same class. |
| `ForeignKey` as `ClassVar` metadata | Documents relationships where they belong. Drives schema generation (DDL). Does not affect query building — FK columns are just `col()` fields. |

---

## Open Questions

- **Parameterisation strategy** — pypika does not natively emit `$N` / `%s` placeholders. The `ParameterisedDialect` approach requires either subclassing a pypika dialect or post-processing the SQL string. The former is cleaner but fragile across pypika versions; the latter is more stable but requires careful escaping logic.
- **Dialect config** — should dialect (PostgreSQL vs MySQL vs SQLite placeholder style) live on `table()`, on `AsyncConnection`, or as a module-level global set once at startup?
- **Type stubs for `table()`** — `table(UserModel)` statically returns `type[_TableProxy]`, losing per-field proxy types. A `mypy` plugin or overloaded `__class_getitem__` stub could recover full field-level types. Worth the complexity?
- **DDL generation** — `FieldDef`, `Index`, `Constraint`, and `ForeignKey` contain enough information to emit `CREATE TABLE` / `CREATE INDEX` DDL. Should this live on `table()` as a `.create_ddl()` method?
- **Cache invalidation** — `table()` caches by model class. Tests that register in-memory schemas may need a way to clear the cache. Expose `_TABLE_CACHE.clear()` or a `reset_table_cache()` helper?
- **Transaction API** — `AsyncConnection.transaction()` returns a driver-native context manager. Should the library wrap it for retries, savepoints, or connection pool checkout?
- **`json_agg` portability** — `json_agg` is PostgreSQL. MySQL uses `JSON_ARRAYAGG`. SQLite has no native equivalent. Should `.prefetch()` be PostgreSQL-only, or should `ParameterisedDialect` abstract the aggregation function name?
