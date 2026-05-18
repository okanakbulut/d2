"""Migration system public API (tracer slice — issue 140)."""

from __future__ import annotations

from typing import ClassVar


class Migration:
    """Base class for migration files.

    Subclasses set `name`, `operations`, and optionally override `atomic`,
    `dependencies`, `reverse_operations`.
    """

    name: ClassVar[str] = ""
    operations: ClassVar[list] = []
    reverse_operations: ClassVar[list | None] = None
    dependencies: ClassVar[list[str]] = []
    atomic: ClassVar[bool] = True


__all__ = ["Migration"]
