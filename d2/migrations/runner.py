"""MigrationRunner — tracer slice (issue 140).

Discovers migration files, applies pending ones in name-sorted order, and
records each in `d2_migrations`. Supports `atomic=True` (BEGIN/COMMIT) and
`atomic=False` (no transaction wrap).
"""


from pathlib import Path
from typing import cast

from d2.driver import Driver

from . import Migration
from .operations import CreateIndex, DropIndex, Operation, RunPython, RunSQL
from .replay import load_migration


def _split_sql_statements(sql: str) -> list[str]:
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


_CREATE_TRACKING_TABLE = (
    "CREATE TABLE IF NOT EXISTS d2_migrations ("
    "id SERIAL PRIMARY KEY, "
    "name TEXT NOT NULL UNIQUE, "
    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")"
)


class MigrationRunner:
    def __init__(
        self,
        conn: Driver,
        migrations_dir: str,
        migrations_table: str = "d2_migrations",
    ) -> None:
        self._conn = conn
        self._migrations_dir = Path(migrations_dir)
        self._migrations_table = migrations_table

    def _discover(self) -> list[tuple[str, type[Migration]]]:
        files = sorted(
            p for p in self._migrations_dir.glob("*.py")
            if not p.name.startswith("_")
        )
        return [(p.stem, load_migration(p)) for p in files]

    async def _ensure_tracking_table(self) -> None:
        await self._conn.execute(_CREATE_TRACKING_TABLE)

    async def applied(self) -> list[str]:
        await self._ensure_tracking_table()
        rows = await self._conn.execute(
            f"SELECT name FROM {self._migrations_table} ORDER BY name"
        )
        return [cast(str, r["name"]) for r in rows]

    async def pending(self) -> list[str]:
        applied = set(await self.applied())
        return [name for name, _ in self._discover() if name not in applied]

    async def apply(self) -> list[str]:
        await self._ensure_tracking_table()
        applied = set(await self.applied())
        newly_applied: list[str] = []

        for name, mig_cls in self._discover():
            if name in applied:
                continue
            await self._apply_one(name, mig_cls)
            newly_applied.append(name)

        return newly_applied

    async def _apply_one(self, name: str, mig_cls: type[Migration]) -> None:
        if mig_cls.atomic:
            async with self._conn.transaction():
                await self._run_ops_and_record(name, mig_cls)
        else:
            await self._run_ops_and_record(name, mig_cls)

    async def _run_ops_and_record(self, name: str, mig_cls: type[Migration]) -> None:
        for op in mig_cls.operations:
            try:
                await self._execute_forward(op)
            except Exception:
                self._print_recovery_for(op)
                raise
        await self._conn.execute(
            f"INSERT INTO {self._migrations_table} (name) VALUES ($1)",
            name,
        )

    async def _execute_forward(self, op: Operation) -> None:
        if isinstance(op, RunSQL):
            for stmt in _split_sql_statements(op.sql):
                await self._conn.execute(stmt)
            return
        if isinstance(op, RunPython):
            await op.fn(self._conn)
            return
        # Every other Operation member is a DDL op with a `to_ddl()` method.
        await self._conn.execute(op.to_ddl())

    async def rollback(self, name: str, *, force: bool = False) -> None:
        await self._ensure_tracking_table()
        applied = await self.applied()
        if not force:
            if not applied or applied[-1] != name:
                raise RuntimeError(
                    f"refusing to rollback {name!r}: not the most recently "
                    "applied migration (use force=True to override)"
                )
        # Locate the migration class.
        mig_cls: type[Migration] | None = None
        for discovered_name, cls in self._discover():
            if discovered_name == name:
                mig_cls = cls
                break
        if mig_cls is None:
            raise RuntimeError(f"migration {name!r} not found on disk")
        if mig_cls.reverse_operations is None:
            raise RuntimeError(
                f"migration {name!r} has reverse_operations = None; "
                "edit the migration file to provide an explicit reverse list"
            )
        if mig_cls.atomic:
            async with self._conn.transaction():
                await self._run_reverse_and_unrecord(name, mig_cls)
        else:
            await self._run_reverse_and_unrecord(name, mig_cls)

    async def _run_reverse_and_unrecord(
        self, name: str, mig_cls: type[Migration]
    ) -> None:
        for op in mig_cls.reverse_operations or []:
            try:
                await self._execute_reverse(op, name)
            except Exception:
                self._print_recovery_for(op)
                raise
        await self._conn.execute(
            f"DELETE FROM {self._migrations_table} WHERE name = $1",
            name,
        )

    async def _execute_reverse(self, op: Operation, name: str) -> None:
        if isinstance(op, RunSQL):
            if op.reverse_sql is None:
                raise RuntimeError(
                    f"cannot rollback {name!r}: RunSQL is missing reverse_sql; "
                    "edit the migration file to provide one"
                )
            for stmt in _split_sql_statements(op.reverse_sql):
                await self._conn.execute(stmt)
            return
        if isinstance(op, RunPython):
            if op.reverse_fn is None:
                raise RuntimeError(
                    f"cannot rollback {name!r}: RunPython is missing reverse_fn; "
                    "edit the migration file to provide one"
                )
            await op.reverse_fn(self._conn)
            return
        await self._conn.execute(op.to_ddl())

    def _print_recovery_for(self, op: Operation) -> None:
        if isinstance(op, CreateIndex) and op.concurrent:
            qual = (
                f'"{op.schema}"."{op.name}"' if op.schema else f'"{op.name}"'
            )
            print(
                "Migration failed during CONCURRENTLY index creation. "
                "An INVALID index may be left behind; recover with:"
            )
            print(f"  DROP INDEX CONCURRENTLY IF EXISTS {qual};")
        elif isinstance(op, DropIndex) and op.concurrent:
            qual = (
                f'"{op.schema}"."{op.name}"' if op.schema else f'"{op.name}"'
            )
            print(
                "Migration failed during CONCURRENTLY index drop; "
                "retry after manual cleanup:"
            )
            print(f"  DROP INDEX CONCURRENTLY IF EXISTS {qual};")
