"""DDL operation dataclasses.

Tracer slice (issue 140) implements `CreateTable` + `ColumnDef` only.
Each op has `apply(state)` (mutates SchemaState) and `to_ddl()` (returns SQL).
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import ColumnState, SchemaError, SchemaState, TableState, ViewState


# SERIAL macro → underlying integer type. Per ADR-0004, state stores the
# integer type and a `_has_sequence_default` flag; DDL still emits the macro.
_SERIAL_TO_INT: dict[str, str] = {
    "SERIAL": "INTEGER",
    "BIGSERIAL": "BIGINT",
    "SMALLSERIAL": "SMALLINT",
}


@dataclass
class ColumnDef:
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False

    def to_ddl(self, name: str) -> str:
        parts = [f'"{name}"', self.type]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        if self.primary_key:
            parts.append("PRIMARY KEY")
        return " ".join(parts)

    def to_column_state(self) -> ColumnState:
        upper = self.type.upper()
        if upper in _SERIAL_TO_INT:
            return ColumnState(
                type=_SERIAL_TO_INT[upper],
                nullable=self.nullable,
                default=self.default,
                primary_key=self.primary_key,
                _has_sequence_default=True,
            )
        return ColumnState(
            type=self.type,
            nullable=self.nullable,
            default=self.default,
            primary_key=self.primary_key,
            _has_sequence_default=False,
        )


def _qualify(schema: str | None, table: str) -> str:
    if schema:
        return f'"{schema}"."{table}"'
    return f'"{table}"'


@dataclass
class CreateTable:
    table: str
    columns: dict[str, ColumnDef]
    schema: str | None = None

    def to_ddl(self) -> str:
        col_ddls = [cd.to_ddl(name) for name, cd in self.columns.items()]
        return (
            f"CREATE TABLE IF NOT EXISTS {_qualify(self.schema, self.table)} "
            f"({', '.join(col_ddls)})"
        )

    def apply(self, state: SchemaState) -> None:
        cols = {name: cd.to_column_state() for name, cd in self.columns.items()}
        state.tables[self.table] = TableState(columns=cols, schema=self.schema)


@dataclass
class DropTable:
    table: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return f"DROP TABLE IF EXISTS {_qualify(self.schema, self.table)}"

    def apply(self, state: SchemaState) -> None:
        state.tables.pop(self.table, None)


def _require_table(state: SchemaState, table: str) -> TableState:
    if table not in state.tables:
        raise SchemaError(f"table {table!r} does not exist")
    return state.tables[table]


def _require_column(state: SchemaState, table: str, column: str) -> ColumnState:
    t = _require_table(state, table)
    if column not in t.columns:
        raise SchemaError(f"column {column!r} does not exist on {table!r}")
    return t.columns[column]


@dataclass
class AddColumn:
    table: str
    column: str
    type: str
    nullable: bool = True
    default: str | None = None
    schema: str | None = None

    def to_ddl(self) -> str:
        parts = [
            f"ALTER TABLE {_qualify(self.schema, self.table)} ADD COLUMN",
            f'"{self.column}"',
            self.type,
        ]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        return " ".join(parts)

    def apply(self, state: SchemaState) -> None:
        t = _require_table(state, self.table)
        if self.column in t.columns:
            raise SchemaError(
                f"column {self.column!r} already exists on {self.table!r}"
            )
        t.columns[self.column] = ColumnState(
            type=self.type,
            nullable=self.nullable,
            default=self.default,
            primary_key=False,
        )


@dataclass
class DropColumn:
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'DROP COLUMN "{self.column}"'
        )

    def apply(self, state: SchemaState) -> None:
        _require_column(state, self.table, self.column)
        del state.tables[self.table].columns[self.column]


@dataclass
class RenameColumn:
    table: str
    old_name: str
    new_name: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'RENAME COLUMN "{self.old_name}" TO "{self.new_name}"'
        )

    def apply(self, state: SchemaState) -> None:
        t = _require_table(state, self.table)
        if self.old_name not in t.columns:
            raise SchemaError(
                f"column {self.old_name!r} does not exist on {self.table!r}"
            )
        if self.new_name in t.columns:
            raise SchemaError(
                f"column {self.new_name!r} already exists on {self.table!r}"
            )
        # Preserve insertion order while renaming the key in place.
        new_columns: dict[str, ColumnState] = {}
        for name, col in t.columns.items():
            if name == self.old_name:
                new_columns[self.new_name] = col
            else:
                new_columns[name] = col
        t.columns = new_columns


@dataclass
class AlterColumnType:
    table: str
    column: str
    type: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" TYPE {self.type}'
        )

    def apply(self, state: SchemaState) -> None:
        col = _require_column(state, self.table, self.column)
        col.type = self.type


@dataclass
class SetColumnNotNull:
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" SET NOT NULL'
        )

    def apply(self, state: SchemaState) -> None:
        col = _require_column(state, self.table, self.column)
        col.nullable = False


@dataclass
class DropColumnNotNull:
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" DROP NOT NULL'
        )

    def apply(self, state: SchemaState) -> None:
        col = _require_column(state, self.table, self.column)
        col.nullable = True


@dataclass
class SetColumnDefault:
    table: str
    column: str
    default: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" SET DEFAULT {self.default}'
        )

    def apply(self, state: SchemaState) -> None:
        col = _require_column(state, self.table, self.column)
        col.default = self.default


@dataclass
class DropColumnDefault:
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" DROP DEFAULT'
        )

    def apply(self, state: SchemaState) -> None:
        col = _require_column(state, self.table, self.column)
        col.default = None


def _quote_cols(cols: tuple[str, ...]) -> str:
    return ", ".join(f'"{c}"' for c in cols)


def _constraint_sql(constraint: dict) -> str:
    ctype = constraint["type"]
    name = constraint["name"]
    if ctype == "unique":
        cols = _quote_cols(tuple(constraint["columns"]))
        return f'CONSTRAINT "{name}" UNIQUE ({cols})'
    if ctype == "foreign_key":
        cols = _quote_cols(tuple(constraint["columns"]))
        ref_schema = constraint.get("references_schema")
        ref_table = constraint["references_table"]
        ref_col = constraint["references_column"]
        ref_qualified = _qualify(ref_schema, ref_table)
        parts = [
            f'CONSTRAINT "{name}" FOREIGN KEY ({cols}) '
            f'REFERENCES {ref_qualified} ("{ref_col}")',
        ]
        on_delete = constraint.get("on_delete")
        on_update = constraint.get("on_update")
        if on_delete:
            parts.append(f"ON DELETE {on_delete}")
        if on_update:
            parts.append(f"ON UPDATE {on_update}")
        return " ".join(parts)
    raise ValueError(f"unsupported constraint type: {ctype!r}")


@dataclass
class AddConstraint:
    table: str
    constraint: dict
    schema: str | None = None

    def to_ddl(self) -> str:
        body = (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f"ADD {_constraint_sql(self.constraint)};"
        )
        return (
            "DO $$ BEGIN "
            f"{body} "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )

    def apply(self, state: SchemaState) -> None:
        t = _require_table(state, self.table)
        t.constraints.append(dict(self.constraint))


@dataclass
class DropConstraint:
    table: str
    name: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {_qualify(self.schema, self.table)} "
            f'DROP CONSTRAINT IF EXISTS "{self.name}"'
        )

    def apply(self, state: SchemaState) -> None:
        t = _require_table(state, self.table)
        t.constraints = [c for c in t.constraints if c.get("name") != self.name]


@dataclass
class CreateIndex:
    table: str
    columns: tuple[str, ...]
    name: str
    method: str | None = None
    unique: bool = False
    concurrent: bool = True
    schema: str | None = None

    def to_ddl(self) -> str:
        parts = ["CREATE"]
        if self.unique:
            parts.append("UNIQUE")
        parts.append("INDEX")
        if self.concurrent:
            parts.append("CONCURRENTLY")
        parts.append("IF NOT EXISTS")
        parts.append(f'"{self.name}"')
        parts.append("ON")
        parts.append(_qualify(self.schema, self.table))
        if self.method:
            parts.append(f"USING {self.method}")
        parts.append(f"({_quote_cols(self.columns)})")
        return " ".join(parts)

    def apply(self, state: SchemaState) -> None:
        t = _require_table(state, self.table)
        t.indexes.append(
            {
                "name": self.name,
                "columns": tuple(self.columns),
                "unique": self.unique,
                "method": self.method,
            }
        )


@dataclass
class DropIndex:
    name: str
    concurrent: bool = True
    schema: str | None = None
    # `table` retained on state when applied for replay; not used in DDL.
    table: str | None = None

    def to_ddl(self) -> str:
        parts = ["DROP INDEX"]
        if self.concurrent:
            parts.append("CONCURRENTLY")
        parts.append("IF EXISTS")
        if self.schema:
            parts.append(f'"{self.schema}"."{self.name}"')
        else:
            parts.append(f'"{self.name}"')
        return " ".join(parts)

    def apply(self, state: SchemaState) -> None:
        for table in state.tables.values():
            table.indexes = [i for i in table.indexes if i.get("name") != self.name]


@dataclass
class CreateView:
    name: str
    definition: str
    schema: str | None = None
    columns: tuple[tuple[str, type], ...] = ()
    replace: bool = True

    def to_ddl(self) -> str:
        head = "CREATE OR REPLACE VIEW" if self.replace else "CREATE VIEW"
        return f"{head} {_qualify(self.schema, self.name)} AS {self.definition}"

    def apply(self, state: SchemaState) -> None:
        state.views[self.name] = ViewState(
            definition=self.definition,
            columns=tuple(self.columns),
            schema=self.schema,
        )


@dataclass
class DropView:
    name: str
    schema: str | None = None
    cascade: bool = False

    def to_ddl(self) -> str:
        sql = f"DROP VIEW IF EXISTS {_qualify(self.schema, self.name)}"
        if self.cascade:
            sql += " CASCADE"
        return sql

    def apply(self, state: SchemaState) -> None:
        state.views.pop(self.name, None)
