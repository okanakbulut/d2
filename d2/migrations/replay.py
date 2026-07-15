"""Migration file loading and replay-into-SchemaState."""

import importlib.util
from pathlib import Path
from typing import Iterable

from . import Migration
from .state import SchemaState


def load_migration(path: Path) -> type[Migration]:
    """Import a migration file by path and return its `Migration` subclass.

    Looks for a class named `Migration` in the loaded module that is a strict
    subclass of `d2.migrations.Migration`.
    """
    spec = importlib.util.spec_from_file_location(f"_d2_mig_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load migration file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidate = getattr(module, "Migration", None)
    if (
        candidate is None
        or not isinstance(candidate, type)
        or not issubclass(candidate, Migration)
        or candidate is Migration
    ):
        raise ImportError(
            f"migration file {path} does not define a Migration subclass"
        )
    return candidate


def replay_migrations(paths: Iterable[Path]) -> SchemaState:
    """Apply each migration's operations onto a fresh `SchemaState`.

    Paths are applied in lexicographic order of their filenames.
    """
    state = SchemaState()
    for path in sorted(paths, key=lambda p: p.name):
        mig_cls = load_migration(path)
        for op in mig_cls.operations:
            op.apply(state)
    return state


# Backwards-compatible alias for the renamed loader.
_load_migration = load_migration
