# Typed Query Builder — Requirements Specification

> A Python library for building SQL queries in a type-safe, IDE-friendly way.
> This document describes **what** the library must do, not how it is implemented.

---

## Problem Statement

Existing Python SQL abstractions force a choice between two unsatisfying extremes:

- **Raw SQL / string builders** — flexible but untyped. Column names are strings. Typos surface at runtime. Values are often interpolated, creating SQL injection risk. No IDE support.
- **Full ORMs** — typed but opinionated. Model classes carry persistence logic, lifecycle hooks, and session state. Query building and IO are entangled. Testing is hard.

This library occupies the middle ground: **typed query construction with zero persistence coupling**. Models are plain structural contracts. Queries are immutable value objects. IO is a separate, thin async layer. Result deserialization is handled by msgspec.

---

## Stakeholders and Use Cases

| Stakeholder | Primary need |
|---|---|
| Application developer | Build complex queries with full IDE autocomplete and type checking |
| Code reviewer | Read query logic that looks like the SQL it produces |
| DBA / architect | Define schema constraints, indexes, and FK relationships in one place |
| Test author | Compose and inspect queries without a database connection |
| Library integrator | Plug in any async database driver without adapting the query layer |

---

## Scope

**In scope:**
- Model definition (tables, views, columns, constraints, relationships)
- Query building: SELECT, INSERT, UPDATE, DELETE, UPSERT
- Joins, subqueries, CTEs (including recursive), unions, set operations
- Aggregations, window functions, scalar functions
- Nested prefetch via single-query JSON aggregation
- Parameterised output — SQL string and bound parameters, always separate
- Async-only execution layer
- Result deserialization via msgspec

**Out of scope:**
- Schema migration (DDL execution)
- Connection pooling
- Caching or query result memoization
- ORM-style lifecycle hooks (before_save, after_create, etc.)
- Sync execution

---

## Core Requirements

### R1 — Model Definitions Are Structural Contracts

Models must be declared as Python `Protocol` classes. They carry no runtime state, no base class dependency, and no persistence logic. A class satisfies the model contract by having the right field declarations — no explicit registration is required.

Each field on a model declares:
- Its Python type (used for `FieldProxy` typing and result deserialization)
- Optional column metadata: primary key, server-side default, uniqueness, index, SQL column name override

A model may additionally declare at the class level:
- Foreign key relationships to other models
- Composite indexes and partial indexes
- Table-level CHECK or UNIQUE constraints
- Explicit table name and schema overrides

Models have no knowledge of query building, connection management, or serialization.

---

### R2 — Table and Schema Names Are Inferred by Convention

By default, a model's table name is derived from its class name and its schema name from its module path. No explicit declaration is needed for standard project layouts.

Convention rules:
- A trailing `Model` suffix is stripped from the class name
- `CamelCase` is converted to `snake_case` for the table name
- The schema name is derived from the module path segment immediately before `models`

Both the table name and schema name can be overridden explicitly when the convention does not apply — for example, when targeting a legacy database or a view with a non-standard name.

---

### R3 — Column References Are Always Typed Proxies

Column references used in query building must always be typed proxy objects, never plain strings. Every column declared on a model is accessible as a named attribute on the corresponding table proxy object.

Column proxies must support:
- Equality, inequality, and ordering comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`)
- String predicates: `LIKE`, `ILIKE`
- List predicates: `IN`, `NOT IN`
- Null predicates: `IS NULL`, `IS NOT NULL`
- Range predicate: `BETWEEN`
- Aggregation: `COUNT` (with optional `DISTINCT`), `SUM`, `AVG`, `MIN`, `MAX`
- Scalar functions: `COALESCE`, `CAST`
- Arithmetic: `+`, `-`, `*`, `/` (for use in `UPDATE SET col = col + 1` expressions)
- Window function specification: `OVER (PARTITION BY ... ORDER BY ...)`
- Column aliasing: rename a column in the SELECT output
- Assignment for UPDATE: produce a typed `SET col = value` expression

No raw string column references are permitted at any call site in the query building API.

---

### R4 — Query Builders Are Immutable

Every query builder method must return a new query builder instance. The original instance must not be modified. This allows:
- Branching a base query into multiple variants without copying
- Safely storing partial queries as shared module-level constants
- Passing query builders between functions without defensive copying

Mutation of a query builder object, whether accidental or intentional, must be a hard error.

---

### R5 — SQL and Parameters Are Always Separate

The query materialisation method must return a `(sql, params)` pair. Literal values passed to any predicate or expression must never be interpolated into the SQL string. They must always be collected as ordered bound parameters and returned separately.

This requirement is absolute. It applies to:
- WHERE clause literals
- INSERT values
- UPDATE SET values
- HAVING clause literals
- Any value passed to a column proxy comparison or function

The SQL string must contain only positional placeholders (e.g. `$1`, `$2`, ...) where values appear. The choice of placeholder style (PostgreSQL `$N` vs. `%s`) is a dialect configuration concern, not a call-site concern.

---

### R6 — All IO Is Async

All operations that interact with a database must be declared as `async def`. There must be no synchronous execution path. The query builder layer itself performs no IO — it only produces `(sql, params)`. The execution layer accepts a `QueryBuilder` and a target result type and returns deserialized results.

The execution layer must support at minimum:
- Fetching a list of results
- Fetching a single optional result
- Fetching a scalar value
- Executing a write (INSERT / UPDATE / DELETE) and returning a status or affected-row count
- Executing within an async transaction context

---

### R7 — Result Deserialization Uses msgspec

Query results must be deserialized into `msgspec.Struct` subclasses. Result structs have no relationship to model protocol classes — they are independent types defined by the application for each query's output shape.

The deserialization layer must use `msgspec.convert` to map row dictionaries onto result structs. This provides:
- Type coercion (e.g. DB `text` → Python `str`, DB `null` → Python `None`)
- Validation of required fields
- Support for nested struct fields (used by prefetch)

A single result struct type can represent:
- A single table's columns (standard query)
- A subset of columns (projection query)
- Columns from multiple tables (join query)
- Columns plus nested list fields populated by prefetch

---

### R8 — Subqueries Are Typed Inline Views

A `QueryBuilder` must be promotable to a named inline view. The result of this promotion is a **subquery proxy** — an object that exposes the subquery's output columns as typed `FieldProxy` attributes, scoped to the subquery's alias.

A subquery proxy must be usable anywhere a table proxy is usable:
- As a JOIN target (the subquery appears in the `FROM` clause)
- In a WHERE condition (typed column reference on the subquery's output)
- In a SELECT list (project a subquery output column)

This mechanism is unified: CTEs and inline subqueries both produce subquery proxies. The outer query references their output columns through the same typed attribute interface, with no string column references.

A `QueryBuilder` must also be promotable to a scalar subquery for use in scalar comparisons (e.g. `WHERE age > (SELECT AVG(age) FROM users)`).

---

### R9 — Joins Support All Standard Types

The query builder must support:
- `INNER JOIN`
- `LEFT JOIN`
- `RIGHT JOIN`
- `CROSS JOIN`

The join condition must be expressed as a criterion built from `FieldProxy` comparisons on both sides. Both sides of a join condition may reference table proxies, aliased table proxies, or subquery proxies.

---

### R10 — Aliasing Is Supported at Every Level

The library must support aliasing at all levels:

- **Column alias** — rename a column in the SELECT output (`Users.name.as_("author")`)
- **Table alias** — create an aliased proxy for a model, used in self-joins and CTE references (`table(EmployeeModel, alias="mgr")`)
- **Subquery alias** — name an inline view produced by `.as_view("alias")`
- **CTE alias** — name a Common Table Expression registered with `.with_cte("name", qb)`

In all cases, the alias-scoped column proxies are the only valid way to reference columns belonging to that alias in the outer query.

---

### R11 — CTEs Including Recursive CTEs Are Supported

The query builder must support:

- **Named CTEs** — a `QueryBuilder` can be registered as a named CTE on another `QueryBuilder`. The CTE's output columns are accessible via a subquery proxy derived from the CTE.
- **Recursive CTEs** — an anchor query and a recursive step query are combined with `UNION ALL` into a `WITH RECURSIVE` expression. The recursive step may reference the CTE's own proxy to express the self-referential join.

---

### R12 — Set Operations Are Supported

The following set operations must be supported between two `QueryBuilder` instances of compatible shape:

- `UNION` (deduplicating)
- `UNION ALL` (preserving duplicates)
- `INTERSECT`
- `EXCEPT`

Set operations produce a new `QueryBuilder` and may be further composed with `ORDER BY`, `LIMIT`, and `OFFSET`.

---

### R13 — Aggregations and Window Functions Are Supported

**Aggregations** must be expressible as methods on column proxies. The result is a new typed column proxy that can be aliased, used in a SELECT list, or used in a HAVING condition.

**Window functions** must be expressible as a column proxy operation that specifies `OVER (PARTITION BY ... ORDER BY ...)`. The result is a named expression usable in a SELECT list.

**GROUP BY** and **HAVING** must be supported on the query builder. A HAVING criterion must be built from the same column proxy and aggregation API used in SELECT — not from raw strings.

---

### R14 — Prefetch Uses Single-Query JSON Aggregation

Fetching nested related records must be expressible as a `.prefetch()` call on a `QueryBuilder`. The library must compile all prefetch declarations into a **single SQL query** using correlated JSON aggregation subqueries (`json_agg` on PostgreSQL, equivalent on other dialects).

Requirements:
- Prefetch declarations must live on `QueryBuilder` — there must be no separate builder class for prefetch
- Prefetch must be nestable to arbitrary depth (posts → comments → reactions, etc.)
- Each `.prefetch()` call accepts an optional pre-built `QueryBuilder` for the child table, enabling filtering, ordering, column projection, and further nesting on child rows
- The result column produced by prefetch must be named explicitly and must correspond to a `list[ChildResultStruct]` field on the parent result struct
- `msgspec.convert` must be able to decode the JSON-aggregated column directly into the nested struct list field — no post-processing step

---

### R15 — Foreign Keys, Indexes, and Constraints Are Declared on Models

Schema-level metadata must be co-located with the model definition:

**Foreign keys** declare:
- The referenced model Protocol
- The referenced column name
- `ON DELETE` and `ON UPDATE` behaviours

**Indexes** declare:
- The columns covered (single or composite)
- Whether the index is unique
- An optional partial index condition (SQL WHERE expression)
- An optional explicit name

**Constraints** declare:
- The constraint kind (`CHECK`, `UNIQUE`, `EXCLUDE`)
- The SQL expression for the constraint body
- An optional explicit name

This metadata is used for schema generation (DDL). It does not affect query building.

---

### R16 — INSERT Supports Single Row, Bulk, and Upsert

The library must support:
- **Single-row INSERT** from a plain dict of column → value pairs
- **Bulk INSERT** from a list of dicts with a consistent column set
- **UPSERT** (`INSERT … ON CONFLICT DO UPDATE SET …` / `ON CONFLICT DO NOTHING`) with conflict target expressed as a column proxy

In all cases, server-side default columns (marked `db_default=True` or `primary_key=True`) must be excluded from the INSERT column list by default.

---

### R17 — UPDATE Supports Full and Partial Updates

The library must support:
- **Full column assignment** — one or more `col.set(value)` assignments passed to `.update()`
- **Expression assignment** — `col.set(col + 1)` for in-place arithmetic using the column proxy's arithmetic operators
- **Partial update from a dict** — a dict of `{column: value}` pairs (e.g. from `msgspec.to_builtins` on a patch struct with `omit_defaults=True`) can be converted to a list of assignments and passed to `.update()`

All UPDATE operations must be chainable with `.where()` to restrict affected rows.

---

## Non-Functional Requirements

### NF1 — Type Safety and IDE Support

- All public API surfaces must be fully typed
- `FieldProxy` attributes on table proxies must be visible to static type checkers and IDEs as named attributes — not dict lookups or `__getattr__` fallbacks
- A typo in a column name must be catchable by the type checker or at class-creation time, not at SQL execution time

### NF2 — Immutability as a Correctness Guarantee

- `QueryBuilder` objects must enforce immutability at runtime, not just by convention
- `SubqueryProxy` objects must also be immutable once created

### NF3 — No SQL Injection Surface

- The public API must make it structurally impossible to interpolate a user-supplied value into the SQL string
- The only path from a value to the database is through the bound parameters tuple returned by `.build()`

### NF4 — Driver Agnosticism

- The query building layer must have zero dependency on any specific database driver
- The execution layer must be thin enough to swap drivers (asyncpg, psycopg3, aiosqlite) by changing the connection wrapper, not the query building code

### NF5 — Single Query Per Operation

- Prefetch must not issue secondary queries. The JSON aggregation approach must be the only supported prefetch mechanism.
- No N+1 query patterns must be possible through the public API

### NF6 — Testability Without a Database

- A `QueryBuilder` must be fully inspectable without a database connection
- `.build()` must be callable in unit tests to assert the SQL string and parameter tuple without executing against a real database

---

## Constraints and Explicit Exclusions

| Constraint | Rationale |
|---|---|
| No `pypika.Field(...)` at any call site | Raw field construction bypasses the typed proxy layer and defeats the type safety guarantee |
| No string column names in predicates or joins | Same reason — all column references must go through `FieldProxy` attributes |
| No sync IO | Mixing sync and async execution leads to event loop blocking bugs |
| No ORM features | Lifecycle hooks, lazy loading, identity map, dirty tracking — none of these belong in a query builder |
| `msgspec.Struct` only for results | Model protocols must have no msgspec dependency; result structs must have no query-building capability |
| No separate builder subclasses for specific operations | Prefetch, CTEs, set operations, and DML must all be methods on a single `QueryBuilder` type |

---

## Glossary

| Term | Definition |
|---|---|
| **Model** | A `Protocol` class that declares a table or view's columns and schema metadata |
| **Table proxy** | A generated class derived from a model; exposes column proxies as named class attributes and query entry-point methods |
| **`FieldProxy`** | A typed handle to a single column or expression; used to build predicates, projections, and assignments |
| **`QueryBuilder`** | An immutable object representing a SQL query under construction; returned by table proxy methods and further composed via chaining |
| **`SubqueryProxy`** | A typed inline view produced by promoting a `QueryBuilder` to a named alias; exposes output columns as `FieldProxy` attributes for use in outer queries |
| **Prefetch** | A `.prefetch()` declaration on a `QueryBuilder` that causes child rows to be fetched via a correlated `json_agg` subquery compiled into the same SQL statement |
| **Result struct** | A `msgspec.Struct` subclass used exclusively to deserialize query results; independent of model definitions |
| **Parameterised output** | The `(sql, params)` pair returned by `.build()`; the SQL string contains only placeholders, never interpolated values |
| **CTE** | Common Table Expression — a named subquery prepended to a SELECT with `WITH` or `WITH RECURSIVE` |

---

## Open Questions

| # | Question | Impact |
|---|---|---|
| 1 | **Placeholder style** — `$N` (PostgreSQL / asyncpg) vs `%s` (psycopg3, MySQL)? Should this be a per-connection setting or a global dialect config? | Affects `.build()` output format and driver compatibility |
| 2 | **`json_agg` portability** — PostgreSQL has `json_agg`, MySQL has `JSON_ARRAYAGG`, SQLite has no equivalent. Is prefetch PostgreSQL-only in v1, or is a dialect abstraction required from the start? | Affects scope of prefetch feature |
| 3 | **Static type recovery for `table()`** — `table(UserModel)` returns a type the static checker sees as `type[_TableProxy]`, losing per-field proxy types. Is a `mypy` plugin, code generation step, or `__class_getitem__` stub required, or is runtime discoverability sufficient? | Affects IDE autocomplete and static analysis |
| 4 | **DDL generation** — models carry enough metadata for `CREATE TABLE` / `CREATE INDEX` DDL. Is this in scope as a utility method, or deferred to a separate migration tool? | Determines whether schema metadata is complete enough at definition time |
| 5 | **Transaction API** — should the library provide its own transaction abstraction (with retry, savepoint support), or delegate entirely to the driver's native transaction API? | Affects connection layer design |
| 6 | **Cache invalidation** — table proxies are cached by model class. Test suites may need to register different in-memory schemas. Is a `reset_cache()` utility needed? | Affects testability |
| 7 | **Partial update ergonomics** — converting a msgspec patch struct to a list of assignments requires a manual `getattr` loop. Should the library provide a helper that accepts a patch struct directly and produces assignments? | Affects UPDATE call-site ergonomics |
