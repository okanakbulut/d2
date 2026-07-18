"""DDL operation dataclasses.

Tracer slice (issue 140) implements `CreateTable` + `ColumnDef` only.
Each op has `apply(state)` (mutates SchemaState) and `to_ddl()` (returns SQL).
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ClassVar, Union

from .state import (
    ColumnState,
    Constraint,
    ConstraintDict,
    ForeignKeyConstraint,
    IndexDef,
    IndexDict,
    SchemaError,
    SchemaState,
    TableState,
    UniqueConstraint,
    ViewState,
    serial_display_type,
)

from d2.driver import Driver

# Re-exported for callers that import these from operations.
__all_aliases__ = ("ConstraintDict", "IndexDict")
ConstraintList = list[ConstraintDict]
IndexList = list[IndexDict]
RunPythonFn = Callable[[Driver], Awaitable[None]]

# Backward-compatible alias: migration files on disk use ColumnDef(...).
# ColumnState normalizes SERIAL types in __post_init__ so ColumnDef(type="BIGSERIAL", ...)
# behaves identically to the old ColumnDef.to_column_state() path.
ColumnDef = ColumnState


# ---------------------------------------------------------------------------
# Op registry — auto-populated via _OpBase.__init_subclass__
# ---------------------------------------------------------------------------

OP_REGISTRY: dict[str, type] = {}


class _OpBase:
    """Non-dataclass mixin that registers each concrete op class by its import name."""

    _import_name: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = cls.__dict__.get("_import_name")
        if name is not None:
            OP_REGISTRY[name] = cls


# ---------------------------------------------------------------------------
# Source-rendering helpers (used by to_source() methods below)
# ---------------------------------------------------------------------------

def _q(value: Any) -> str:
    """Render a Python literal preferring double-quoted strings."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return repr(value)


def _format_columndef(cd: ColumnState) -> str:
    display_type = serial_display_type(cd.type, cd.has_sequence_default)
    return (
        f"ColumnDef(type={_q(display_type)}, nullable={_q(cd.nullable)}, "
        f"default={_q(cd.default)}, primary_key={_q(cd.primary_key)})"
    )


def _format_columns_tuple(cols: tuple[str, ...]) -> str:
    inside = ", ".join(_q(c) for c in cols)
    if len(cols) == 1:
        return f"({inside},)"
    return f"({inside})"


def _format_type(t: type) -> str:
    mod = getattr(t, "__module__", "builtins")
    name = getattr(t, "__qualname__", t.__name__)
    if mod == "builtins":
        return name
    return f"{mod}.{name}"


def _format_view_columns(cols: tuple[tuple[str, type], ...]) -> str:
    if not cols:
        return "()"
    parts = [f"({_q(n)}, {_format_type(t)})" for n, t in cols]
    if len(parts) == 1:
        return f"({parts[0]},)"
    return "(" + ", ".join(parts) + ")"


def _format_constraint(c: Constraint | ConstraintDict) -> str:
    """Render a constraint as a dict literal string for migration files."""
    if isinstance(c, UniqueConstraint):
        cols = "(" + ", ".join(_q(x) for x in c.columns) + (",)" if len(c.columns) == 1 else ")")
        parts = [
            f'"type": {_q("unique")}',
            f'"name": {_q(c.name)}',
            f'"columns": {cols}',
        ]
        return "{" + ", ".join(parts) + "}"
    if isinstance(c, ForeignKeyConstraint):
        cols = "(" + ", ".join(_q(x) for x in c.columns) + (",)" if len(c.columns) == 1 else ")")
        parts = [
            f'"type": {_q("foreign_key")}',
            f'"name": {_q(c.name)}',
            f'"columns": {cols}',
            f'"references_schema": {_q(c.references_schema)}',
            f'"references_table": {_q(c.references_table)}',
            f'"references_column": {_q(c.references_column)}',
            f'"on_delete": {_q(c.on_delete)}',
            f'"on_update": {_q(c.on_update)}',
        ]
        return "{" + ", ".join(parts) + "}"
    # Plain dict — backward compat path for callers that build ops manually.
    cols = "(" + ", ".join(_q(x) for x in c["columns"]) + (",)" if len(c["columns"]) == 1 else ")")
    parts = [
        f'"type": {_q(c["type"])}',
        f'"name": {_q(c["name"])}',
        f'"columns": {cols}',
    ]
    if c["type"] == "foreign_key":
        parts.append(f'"references_schema": {_q(c.get("references_schema"))}')
        parts.append(f'"references_table": {_q(c["references_table"])}')
        parts.append(f'"references_column": {_q(c["references_column"])}')
        parts.append(f'"on_delete": {_q(c.get("on_delete"))}')
        parts.append(f'"on_update": {_q(c.get("on_update"))}')
    return "{" + ", ".join(parts) + "}"


def qualify(schema: str | None, table: str) -> str:
    if schema:
        return f'"{schema}"."{table}"'
    return f'"{table}"'


@dataclass
class CreateTable(_OpBase):
    _import_name: ClassVar[str] = "CreateTable"
    table: str
    columns: dict[str, ColumnDef]
    schema: str | None = None

    def to_ddl(self) -> str:
        col_ddls = [cd.to_ddl(name) for name, cd in self.columns.items()]
        return (
            f"CREATE TABLE IF NOT EXISTS {qualify(self.schema, self.table)} "
            f"({', '.join(col_ddls)})"
        )

    def to_source(self, indent: str) -> str:
        lines = [f"{indent}CreateTable("]
        lines.append(f"{indent}    table={_q(self.table)},")
        lines.append(f"{indent}    schema={_q(self.schema)},")
        lines.append(f"{indent}    columns={{")
        for col_name, cd in self.columns.items():
            lines.append(f"{indent}        {_q(col_name)}: {_format_columndef(cd)},")
        lines.append(f"{indent}    }},")
        lines.append(f"{indent}),")
        return "\n".join(lines)

    def apply(self, state: SchemaState) -> None:
        state.tables[self.table] = TableState(columns=dict(self.columns), schema=self.schema)


@dataclass
class DropTable(_OpBase):
    _import_name: ClassVar[str] = "DropTable"
    table: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return f"DROP TABLE IF EXISTS {qualify(self.schema, self.table)}"

    def to_source(self, indent: str) -> str:
        return f"{indent}DropTable(table={_q(self.table)}, schema={_q(self.schema)}),"

    def apply(self, state: SchemaState) -> None:
        state.tables.pop(self.table, None)


def require_table(state: SchemaState, table: str) -> TableState:
    if table not in state.tables:
        raise SchemaError(f"table {table!r} does not exist")
    return state.tables[table]


def require_column(state: SchemaState, table: str, column: str) -> ColumnState:
    t = require_table(state, table)
    if column not in t.columns:
        raise SchemaError(f"column {column!r} does not exist on {table!r}")
    return t.columns[column]


@dataclass
class AddColumn(_OpBase):
    _import_name: ClassVar[str] = "AddColumn"
    table: str
    column: str
    type: str
    nullable: bool = True
    default: str | None = None
    schema: str | None = None

    def to_ddl(self) -> str:
        parts = [
            f"ALTER TABLE {qualify(self.schema, self.table)} ADD COLUMN IF NOT EXISTS",
            f'"{self.column}"',
            self.type,
        ]
        if not self.nullable:
            parts.append("NOT NULL")
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        return " ".join(parts)

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}AddColumn(table={_q(self.table)}, column={_q(self.column)}, "
            f"type={_q(self.type)}, nullable={_q(self.nullable)}, "
            f"default={_q(self.default)}, schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        t = require_table(state, self.table)
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
class DropColumn(_OpBase):
    _import_name: ClassVar[str] = "DropColumn"
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'DROP COLUMN IF EXISTS "{self.column}"'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropColumn(table={_q(self.table)}, column={_q(self.column)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        require_column(state, self.table, self.column)
        del state.tables[self.table].columns[self.column]


@dataclass
class RenameColumn(_OpBase):
    _import_name: ClassVar[str] = "RenameColumn"
    table: str
    old_name: str
    new_name: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'RENAME COLUMN "{self.old_name}" TO "{self.new_name}"'
        )

    def apply(self, state: SchemaState) -> None:
        t = require_table(state, self.table)
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

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}RenameColumn(table={_q(self.table)}, "
            f"old_name={_q(self.old_name)}, new_name={_q(self.new_name)}, "
            f"schema={_q(self.schema)}),"
        )


@dataclass
class AlterColumnType(_OpBase):
    _import_name: ClassVar[str] = "AlterColumnType"
    table: str
    column: str
    type: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" TYPE {self.type}'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}AlterColumnType(table={_q(self.table)}, column={_q(self.column)}, "
            f"type={_q(self.type)}, schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        col = require_column(state, self.table, self.column)
        col.type = self.type


@dataclass
class SetColumnNotNull(_OpBase):
    _import_name: ClassVar[str] = "SetColumnNotNull"
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" SET NOT NULL'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}SetColumnNotNull(table={_q(self.table)}, column={_q(self.column)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        col = require_column(state, self.table, self.column)
        col.nullable = False


@dataclass
class DropColumnNotNull(_OpBase):
    _import_name: ClassVar[str] = "DropColumnNotNull"
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" DROP NOT NULL'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropColumnNotNull(table={_q(self.table)}, column={_q(self.column)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        col = require_column(state, self.table, self.column)
        col.nullable = True


@dataclass
class SetColumnDefault(_OpBase):
    _import_name: ClassVar[str] = "SetColumnDefault"
    table: str
    column: str
    default: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" SET DEFAULT {self.default}'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}SetColumnDefault(table={_q(self.table)}, column={_q(self.column)}, "
            f"default={_q(self.default)}, schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        col = require_column(state, self.table, self.column)
        col.default = self.default


@dataclass
class DropColumnDefault(_OpBase):
    _import_name: ClassVar[str] = "DropColumnDefault"
    table: str
    column: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'ALTER COLUMN "{self.column}" DROP DEFAULT'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropColumnDefault(table={_q(self.table)}, column={_q(self.column)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        col = require_column(state, self.table, self.column)
        col.default = None


def quote_cols(cols: tuple[str, ...]) -> str:
    return ", ".join(f'"{c}"' for c in cols)


def constraint_from_dict(d: ConstraintDict) -> Constraint:
    """Convert a raw constraint dict (from migration files on disk) to a typed object."""
    ctype = d["type"]
    if ctype == "unique":
        return UniqueConstraint(name=d["name"], columns=tuple(d["columns"]))
    if ctype == "foreign_key":
        return ForeignKeyConstraint(
            name=d["name"],
            columns=tuple(d["columns"]),
            references_schema=d.get("references_schema"),
            references_table=d["references_table"],
            references_column=d["references_column"],
            on_delete=d.get("on_delete"),
            on_update=d.get("on_update"),
        )
    raise ValueError(f"unknown constraint type: {ctype!r}")


def constraint_sql(constraint: Constraint) -> str:
    if isinstance(constraint, UniqueConstraint):
        cols = quote_cols(constraint.columns)
        return f'CONSTRAINT "{constraint.name}" UNIQUE ({cols})'
    # ForeignKeyConstraint — the only remaining member of the Constraint union.
    cols = quote_cols(constraint.columns)
    ref_qualified = qualify(constraint.references_schema, constraint.references_table)
    parts = [
        f'CONSTRAINT "{constraint.name}" FOREIGN KEY ({cols}) '
        f'REFERENCES {ref_qualified} ("{constraint.references_column}")',
    ]
    if constraint.on_delete:
        parts.append(f"ON DELETE {constraint.on_delete}")
    if constraint.on_update:
        parts.append(f"ON UPDATE {constraint.on_update}")
    return " ".join(parts)


@dataclass
class AddConstraint(_OpBase):
    _import_name: ClassVar[str] = "AddConstraint"
    table: str
    constraint: ConstraintDict | Constraint
    schema: str | None = None

    def _typed_constraint(self) -> Constraint:
        if isinstance(self.constraint, (UniqueConstraint, ForeignKeyConstraint)):
            return self.constraint
        return constraint_from_dict(self.constraint)

    def to_ddl(self) -> str:
        body = (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f"ADD {constraint_sql(self._typed_constraint())};"
        )
        return (
            "DO $$ BEGIN "
            f"{body} "
            "EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL; END $$"
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}AddConstraint(table={_q(self.table)}, "
            f"constraint={_format_constraint(self.constraint)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        t = require_table(state, self.table)
        t.constraints.append(self._typed_constraint())


@dataclass
class DropConstraint(_OpBase):
    _import_name: ClassVar[str] = "DropConstraint"
    table: str
    name: str
    schema: str | None = None

    def to_ddl(self) -> str:
        return (
            f"ALTER TABLE {qualify(self.schema, self.table)} "
            f'DROP CONSTRAINT IF EXISTS "{self.name}"'
        )

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropConstraint(table={_q(self.table)}, name={_q(self.name)}, "
            f"schema={_q(self.schema)}),"
        )

    def apply(self, state: SchemaState) -> None:
        t = require_table(state, self.table)
        t.constraints = [c for c in t.constraints if c.name != self.name]


@dataclass
class CreateIndex(_OpBase):
    _import_name: ClassVar[str] = "CreateIndex"
    table: str
    columns: tuple[str, ...]
    name: str
    method: str | None = None
    unique: bool = False
    concurrent: bool = True
    schema: str | None = None
    where: str | None = None

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
        parts.append(qualify(self.schema, self.table))
        if self.method:
            parts.append(f"USING {self.method}")
        parts.append(f"({quote_cols(self.columns)})")
        if self.where:
            parts.append(f"WHERE {self.where}")
        return " ".join(parts)

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}CreateIndex(table={_q(self.table)}, "
            f"columns={_format_columns_tuple(tuple(self.columns))}, "
            f"name={_q(self.name)}, method={_q(self.method)}, "
            f"unique={_q(self.unique)}, concurrent={_q(self.concurrent)}, "
            f"schema={_q(self.schema)}, where={_q(self.where)}),"
        )

    def apply(self, state: SchemaState) -> None:
        t = require_table(state, self.table)
        t.indexes.append(
            IndexDef(
                name=self.name,
                columns=tuple(self.columns),
                unique=self.unique,
                method=self.method,
                where=self.where,
            )
        )


@dataclass
class DropIndex(_OpBase):
    _import_name: ClassVar[str] = "DropIndex"
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

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropIndex(name={_q(self.name)}, concurrent={_q(self.concurrent)}, "
            f"schema={_q(self.schema)}, table={_q(self.table)}),"
        )

    def apply(self, state: SchemaState) -> None:
        for table in state.tables.values():
            table.indexes = [i for i in table.indexes if i.name != self.name]


@dataclass
class CreateExtension(_OpBase):
    _import_name: ClassVar[str] = "CreateExtension"
    name: str

    def to_ddl(self) -> str:
        return f'CREATE EXTENSION IF NOT EXISTS "{self.name}"'

    def to_source(self, indent: str) -> str:
        return f"{indent}CreateExtension(name={_q(self.name)}),"

    def apply(self, state: SchemaState) -> None:
        state.extensions.add(self.name)


@dataclass
class DropExtension(_OpBase):
    _import_name: ClassVar[str] = "DropExtension"
    name: str

    def to_ddl(self) -> str:
        return f'DROP EXTENSION IF EXISTS "{self.name}"'

    def to_source(self, indent: str) -> str:
        return f"{indent}DropExtension(name={_q(self.name)}),"

    def apply(self, state: SchemaState) -> None:
        state.extensions.discard(self.name)


@dataclass
class CreateSchema(_OpBase):
    _import_name: ClassVar[str] = "CreateSchema"
    name: str

    def to_ddl(self) -> str:
        return f'CREATE SCHEMA IF NOT EXISTS "{self.name}"'

    def to_source(self, indent: str) -> str:
        return f"{indent}CreateSchema(name={_q(self.name)}),"

    def apply(self, state: SchemaState) -> None:
        state.schemas.add(self.name)


@dataclass
class DropSchema(_OpBase):
    _import_name: ClassVar[str] = "DropSchema"
    name: str
    cascade: bool = False

    def to_ddl(self) -> str:
        sql = f'DROP SCHEMA IF EXISTS "{self.name}"'
        if self.cascade:
            sql += " CASCADE"
        return sql

    def to_source(self, indent: str) -> str:
        return f"{indent}DropSchema(name={_q(self.name)}, cascade={_q(self.cascade)}),"

    def apply(self, state: SchemaState) -> None:
        state.schemas.discard(self.name)


@dataclass
class CreateView(_OpBase):
    _import_name: ClassVar[str] = "CreateView"
    name: str
    definition: str
    schema: str | None = None
    columns: tuple[tuple[str, type[Any]], ...] = ()
    replace: bool = True

    def to_ddl(self) -> str:
        head = "CREATE OR REPLACE VIEW" if self.replace else "CREATE VIEW"
        return f"{head} {qualify(self.schema, self.name)} AS {self.definition}"

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}CreateView(name={_q(self.name)}, "
            f"definition={_q(self.definition)}, schema={_q(self.schema)}, "
            f"columns={_format_view_columns(tuple(self.columns))}, "
            f"replace={_q(self.replace)}),"
        )

    def apply(self, state: SchemaState) -> None:
        state.views[self.name] = ViewState(
            definition=self.definition,
            columns=tuple(self.columns),
            schema=self.schema,
        )


@dataclass
class RunSQL(_OpBase):
    """Data-only escape hatch: execute raw SQL at apply time.

    `apply(state)` is a no-op — RunSQL never mutates the schema model.
    The runner splits `sql` on ``;`` and executes each non-empty statement.
    `reverse_sql`, if provided, is executed on rollback.
    """

    _import_name: ClassVar[str] = "RunSQL"
    sql: str
    reverse_sql: str | None = None

    def to_source(self, indent: str) -> str:  # noqa: ARG002
        raise NotImplementedError("RunSQL/RunPython cannot be serialized to source")

    def apply(self, state: SchemaState) -> None:  # noqa: ARG002
        return None


@dataclass
class RunPython(_OpBase):
    """Data-only escape hatch: run an async Python function at apply time.

    `apply(state)` is a no-op. The runner awaits ``fn(conn)`` where ``conn``
    is a ``Driver`` instance. ``reverse_fn``, if provided, is
    awaited on rollback.
    """

    _import_name: ClassVar[str] = "RunPython"
    fn: RunPythonFn
    reverse_fn: RunPythonFn | None = None

    def to_source(self, indent: str) -> str:  # noqa: ARG002
        raise NotImplementedError("RunSQL/RunPython cannot be serialized to source")

    def apply(self, state: SchemaState) -> None:  # noqa: ARG002
        return None


@dataclass
class DropView(_OpBase):
    _import_name: ClassVar[str] = "DropView"
    name: str
    schema: str | None = None
    cascade: bool = False

    def to_ddl(self) -> str:
        sql = f"DROP VIEW IF EXISTS {qualify(self.schema, self.name)}"
        if self.cascade:
            sql += " CASCADE"
        return sql

    def to_source(self, indent: str) -> str:
        return (
            f"{indent}DropView(name={_q(self.name)}, schema={_q(self.schema)}, "
            f"cascade={_q(self.cascade)}),"
        )

    def apply(self, state: SchemaState) -> None:
        state.views.pop(self.name, None)


# Union of every concrete DDL/data op in this module. Used as the element type
# for `operations` / `reverse_operations` lists and for diff/codegen lists.
Operation = Union[
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    RenameColumn,
    AlterColumnType,
    SetColumnNotNull,
    DropColumnNotNull,
    SetColumnDefault,
    DropColumnDefault,
    AddConstraint,
    DropConstraint,
    CreateIndex,
    DropIndex,
    CreateExtension,
    DropExtension,
    CreateSchema,
    DropSchema,
    CreateView,
    DropView,
    RunSQL,
    RunPython,
]


# Subset of `Operation` whose `to_ddl()` emits SQL — i.e. excludes the data-only
# escape hatches `RunSQL` / `RunPython`. Used to type the dispatch branches in
# the runner that fall through to `raw.execute(op.to_ddl())`.
DDLOperation = Union[
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    RenameColumn,
    AlterColumnType,
    SetColumnNotNull,
    DropColumnNotNull,
    SetColumnDefault,
    DropColumnDefault,
    AddConstraint,
    DropConstraint,
    CreateIndex,
    DropIndex,
    CreateExtension,
    DropExtension,
    CreateSchema,
    DropSchema,
    CreateView,
    DropView,
]
