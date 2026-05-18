"""Minimal migration file loader for the tracer slice."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from . import Migration


def _load_migration(path: Path) -> type[Migration]:
    """Import a migration file by path and return its `Migration` subclass.

    Looks for a class named `Migration` in the loaded module that is a strict
    subclass of `norm.migrations.Migration`.
    """
    spec = importlib.util.spec_from_file_location(f"_norm_mig_{path.stem}", path)
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
