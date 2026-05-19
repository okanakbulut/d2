"""Read `[tool.norm]` from pyproject.toml with conventional fallbacks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class NormConfig:
    migrations_dir: Path
    models: str  # dotted module path


def _read_tool_norm(cwd: Path) -> dict[str, Any]:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.exists():
        return {}
    data: dict[str, Any] = tomllib.loads(pyproject.read_text())
    tool: dict[str, Any] = data.get("tool", {})
    norm: dict[str, Any] = tool.get("norm", {})
    return norm or {}


def _detect_models(cwd: Path) -> str:
    if (cwd / "models.py").exists():
        return "models"
    if (cwd / "models" / "__init__.py").exists():
        return "models"
    raise FileNotFoundError(
        f"no [tool.norm] models setting and no models.py / models/ in {cwd}"
    )


def load_config(
    cwd: Path,
    *,
    migrations_dir_override: str | None = None,
    models_override: str | None = None,
) -> NormConfig:
    """Load configuration for the migrations CLI."""
    tool_norm = _read_tool_norm(cwd)

    migrations_dir_raw: str = (
        migrations_dir_override
        or cast(str | None, tool_norm.get("migrations_dir"))
        or "migrations"
    )
    models: str = (
        models_override
        or cast(str | None, tool_norm.get("models"))
        or _detect_models(cwd)
    )

    migrations_dir = cwd / migrations_dir_raw
    return NormConfig(migrations_dir=migrations_dir, models=models)
