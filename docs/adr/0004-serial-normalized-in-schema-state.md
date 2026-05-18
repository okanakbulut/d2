# `SERIAL`/`BIGSERIAL`/`SMALLSERIAL` are normalized in `SchemaState`

`SchemaState` stores serial-typed columns as their underlying integer type (`INTEGER`/`BIGINT`/`SMALLINT`) plus a `_has_sequence_default: bool` flag on `ColumnState`. DDL emission still uses the `SERIAL` macro for column creation; only the internal state representation is normalized.

## Considered alternatives

- **Store verbatim** (`type="BIGSERIAL"` in state). Rejected because `BIGSERIAL` is a Postgres macro that expands to `BIGINT NOT NULL DEFAULT nextval('seq')` at creation time. If the model later removes `db_default=True`, the correct diff is `DropColumnDefault` — but a verbatim state would show "BIGSERIAL → BIGINT" and emit a spurious type-change `AlterColumnType`. The underlying column type never actually changed.

## Consequences

- The snapshot (model → state) and replay (migration files → state) must apply identical normalization to avoid oscillating diffs.
- `CreateTable` still emits `BIGSERIAL` in column DDL because it's the most concise way to ask Postgres for an integer + identity sequence. The normalization is purely an internal accounting choice.
