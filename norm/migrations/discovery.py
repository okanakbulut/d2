"""Filesystem and import utilities for locating migration files and model classes."""

import importlib
import pkgutil
import sys
from pathlib import Path

from .config import NormConfig
from .registry import MODEL_REGISTRY


def existing_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        return []
    return sorted(p for p in migrations_dir.glob("*.py") if not p.name.startswith("_"))


def next_number(migrations_dir: Path) -> int:
    files = existing_migration_files(migrations_dir)
    highest = 0
    for p in files:
        head = p.stem.split("_", 1)[0]
        if head.isdigit():
            highest = max(highest, int(head))
    return highest + 1


def import_models_module(dotted: str) -> None:
    if dotted in sys.modules:
        module = importlib.reload(sys.modules[dotted])
    else:
        module = importlib.import_module(dotted)
    if hasattr(module, "__path__"):
        for sub in pkgutil.iter_modules(module.__path__):
            full = f"{dotted}.{sub.name}"
            if full in sys.modules:
                importlib.reload(sys.modules[full])
            else:
                importlib.import_module(full)


def models_for(cfg: NormConfig) -> list[type]:
    prefix = cfg.models
    stale = [
        key for key, cls in MODEL_REGISTRY.items()
        if cls.__module__ == prefix or cls.__module__.startswith(prefix + ".")
    ]
    for key in stale:
        del MODEL_REGISTRY[key]

    import_models_module(prefix)

    return [
        cls
        for cls in MODEL_REGISTRY.values()
        if cls.__module__ == prefix or cls.__module__.startswith(prefix + ".")
    ]
