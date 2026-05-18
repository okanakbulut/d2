# 148 — Escape hatches: `RunSQL` / `RunPython` + `check` DDL lint

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

Data-only escape hatches for backfills and seeding. After this slice, a user can hand-write a migration that calls an async Python function or runs raw SQL — typically to seed data, backfill new columns, or perform one-off cleanups. Schema changes must still go through the DDL ops (enforced by `check`).

### Scope

- **`RunSQL(sql, reverse_sql=None)`**: `apply` is a no-op on `SchemaState`. At apply time, runner splits `sql` on `;` and executes each statement.
- **`RunPython(fn, reverse_fn=None)`**: `apply` is a no-op on `SchemaState`. At apply time, runner calls `await fn(conn)` where `conn` is the norm `AsyncConnection` wrapper (NOT raw asyncpg).
- **Rollback dispatch** (from 147): `RunSQL` rollback runs `reverse_sql` if set, raises otherwise; `RunPython` rollback awaits `reverse_fn(conn)` if set, raises otherwise.
- **Codegen**: never auto-emits `RunSQL` or `RunPython` — these are hand-authored. Codegen does preserve them if they appear in `operations` of an existing file (they don't affect diff).
- **`check` DDL lint**: scans each `RunSQL.sql` for top-level DDL keywords (`ALTER`, `CREATE`, `DROP`, `TRUNCATE` — case-insensitive, ignoring strings/comments where reasonable) and emits a warning. `check` exit code is non-zero when any warning fires.

Out of scope: SQL parser; the lint is keyword-based with the understanding that false positives are possible. Users can suppress per-op with `RunSQL(sql=..., allow_ddl=True)` (deferred — not in this slice unless trivially added).

## Acceptance criteria

- [ ] `RunSQL` dataclass exists with `sql: str`, `reverse_sql: str | None = None`; `apply(state)` is a no-op
- [ ] `RunPython` dataclass exists with `fn: Callable[[AsyncConnection], Awaitable[None]]`, `reverse_fn: Callable | None = None`; `apply(state)` is a no-op
- [ ] Runner dispatches `RunSQL` by splitting on `;` and executing each statement
- [ ] Runner dispatches `RunPython` by `await fn(conn)` where `conn` is `norm.AsyncConnection`
- [ ] Rollback: `RunSQL.reverse_sql` runs if set; `RunPython.reverse_fn` awaited if set
- [ ] Rollback raises a clear error pointing at the file when reverse is missing
- [ ] `check` warns (non-zero exit) on DDL keywords in `RunSQL.sql`
- [ ] Codegen never auto-emits `RunSQL` / `RunPython`
- [ ] Unit test: `RunSQL.apply` and `RunPython.apply` do not mutate `SchemaState`
- [ ] Unit test: `check` lint flags `RunSQL("ALTER TABLE foo ...")` and ignores `RunSQL("INSERT INTO foo ...")`
- [ ] Integration test: hand-written migration with `RunPython` backfill → `apply` runs the function with a working `AsyncConnection`; `rollback` runs `reverse_fn`

## Blocked by

- [140 — Tracer: hand-written CreateTable migration through `apply`](140-tracer-create-table-migration.md)
