"""Unit tests for codegen of view ops (issue 145)."""

from pathlib import Path

from typing import Any

from norm.migrations.codegen import make_migration
from norm.migrations.operations import CreateView, DropView


class TestViewCodegen:
    def test_create_view_round_trips(self, tmp_path: Path) -> None:
        op = CreateView(
            name="active_users",
            definition='SELECT "id" FROM "public"."users"',
            schema="public",
            columns=(("id", int),),
            replace=True,
        )
        path = make_migration(
            migrations_dir=tmp_path,
            number=1,
            forward=[op],
            reverse=[DropView(name="active_users", schema="public")],
            dependencies=[],
            label=None,
        )
        text = path.read_text()
        # Execute the generated file and pull its `Migration` class out.
        ns: dict[str, Any] = {}
        exec(text, ns)
        mig = ns["Migration"]
        assert mig.operations == [op]
        assert mig.reverse_operations == [
            DropView(name="active_users", schema="public")
        ]

    def test_drop_view_with_cascade_round_trips(self, tmp_path: Path) -> None:
        op = DropView(name="v", schema=None, cascade=True)
        path = make_migration(
            migrations_dir=tmp_path,
            number=2,
            forward=[op],
            reverse=[],
            dependencies=[],
            label="drop_v",
        )
        ns: dict[str, Any] = {}
        exec(path.read_text(), ns)
        mig = ns["Migration"]
        assert mig.operations == [op]
