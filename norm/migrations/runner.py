"""MigrationRunner — tracer slice (issue 140).

Discovers migration files, applies pending ones in name-sorted order, and
records each in `norm_migrations`. Supports `atomic=True` (BEGIN/COMMIT) and
`atomic=False` (no transaction wrap).
"""

from __future__ import annotations

from pathlib import Path

from norm.connection import AsyncConnection

from . import Migration
from .operations import CreateIndex, DropIndex
from .replay import _load_migration


_CREATE_TRACKING_TABLE = (
    "CREATE TABLE IF NOT EXISTS norm_migrations ("
    "id SERIAL PRIMARY KEY, "
    "name TEXT NOT NULL UNIQUE, "
    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")"
)


class MigrationRunner:
    def __init__(
        self,
        conn: AsyncConnection,
        migrations_dir: str,
        migrations_table: str = "norm_migrations",
    ) -> None:
        self._conn = conn
        self._migrations_dir = Path(migrations_dir)
        self._migrations_table = migrations_table

    def _discover(self) -> list[tuple[str, type[Migration]]]:
        files = sorted(
            p for p in self._migrations_dir.glob("*.py")
            if not p.name.startswith("_")
        )
        return [(p.stem, _load_migration(p)) for p in files]

    async def _ensure_tracking_table(self) -> None:
        await self._conn._conn.execute(_CREATE_TRACKING_TABLE)

    async def applied(self) -> list[str]:
        await self._ensure_tracking_table()
        rows = await self._conn._conn.fetch(
            f"SELECT name FROM {self._migrations_table} ORDER BY name"
        )
        return [r["name"] for r in rows]

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
        raw = self._conn._conn
        if mig_cls.atomic:
            async with raw.transaction():
                await self._run_ops_and_record(name, mig_cls)
        else:
            await self._run_ops_and_record(name, mig_cls)

    async def _run_ops_and_record(self, name: str, mig_cls: type[Migration]) -> None:
        raw = self._conn._conn
        for op in mig_cls.operations:
            try:
                await raw.execute(op.to_ddl())
            except Exception:
                self._print_recovery_for(op)
                raise
        await raw.execute(
            f"INSERT INTO {self._migrations_table} (name) VALUES ($1)",
            name,
        )

    def _print_recovery_for(self, op: object) -> None:
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
