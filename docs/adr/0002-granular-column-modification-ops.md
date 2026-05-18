# Granular column-modification ops instead of a bag-of-options `AlterColumn`

Column modifications are five single-purpose ops — `AlterColumnType`, `SetColumnNotNull`, `DropColumnNotNull`, `SetColumnDefault`, `DropColumnDefault` — each emitting exactly one `ALTER TABLE ... ALTER COLUMN ...` action. There is no combined `AlterColumn(type=, nullable=, default=)`.

## Considered alternatives

- **One `AlterColumn` dataclass with optional fields.** Rejected because (a) `default=None` is ambiguous (no change vs. drop default) and requires a sentinel, (b) the `to_ddl()` branches on which fields are set, and (c) reverse-op generation has to mirror the same multi-optional shape.

## Consequences

- DDL maps 1:1 to op classes — a reader sees exactly which `ALTER COLUMN` action runs.
- A diff that changes type + nullability + default produces three forward ops and three reverse ops. Migration files are longer but more explicit.
- `AddColumn` and `DropColumn` keep their full-spec APIs since they create/remove the column itself; only modifications are granular.
