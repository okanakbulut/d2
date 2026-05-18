"""Read `[tool.norm]` from pyproject.toml with conventional fallbacks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NormConfig:
    migrations_dir: Path
    models: str  # dotted module path


def _read_tool_norm(cwd: Path) -> dict:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.exists():
        return {}
    data = tomllib.loads(pyproject.read_text())
    return data.get("tool", {}).get("norm", {}) or {}


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

    migrations_dir_raw = (
        migrations_dir_override
        or tool_norm.get("migrations_dir")
        or "migrations"
    )
    models = models_override or tool_norm.get("models") or _detect_models(cwd)

    migrations_dir = cwd / migrations_dir_raw
    return NormConfig(migrations_dir=migrations_dir, models=models)
