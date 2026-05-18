# `CreateIndex` and `DropIndex` default to `concurrent=True`

`CreateIndex.concurrent` and `DropIndex.concurrent` default to `True`, emitting `CREATE INDEX CONCURRENTLY` / `DROP INDEX CONCURRENTLY`. Any migration containing a non-transactional op has `atomic = False` set automatically by codegen, with a one-line comment in the generated file explaining why.

## Considered alternatives

- **Default `concurrent=False` (Postgres default).** Rejected because plain `CREATE INDEX` takes an `ACCESS EXCLUSIVE` lock and blocks all reads and writes on the table for the duration — a production-hostile default. Users would have to remember to opt in for every index, which is exactly the kind of footgun that bites once at 2am.
- **Aggressively split migrations** so each non-transactional op is in its own file. Rejected because norm's DDL is already idempotent (`IF [NOT] EXISTS`, exception-wrapped `AddConstraint`), so a partially-applied non-atomic migration can be safely retried. The cost of more migration files exceeds the benefit.

## Consequences

- A failed `CONCURRENTLY` index creation leaves an `INVALID` index in Postgres; the runner prints the exact `DROP INDEX CONCURRENTLY IF EXISTS ...` recovery command and re-raises. The migration is not recorded; retry after manual cleanup.
- `RunSQL` and `RunPython` bodies in non-atomic migrations must be authored to be idempotent. `check` lints `RunSQL` for non-idempotent DDL/data patterns as a warning.
- Codegen always passes `concurrent=True` and `atomic = False` explicitly in generated files, so the behavior is visible without consulting norm's defaults.
