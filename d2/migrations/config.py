"""Read `[tool.d2]` from pyproject.toml with conventional fallbacks."""


import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class D2Config:
    migrations_dir: Path
    models: str  # dotted module path


def _read_tool_d2(cwd: Path) -> dict[str, Any]:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.exists():
        return {}
    data: dict[str, Any] = tomllib.loads(pyproject.read_text())
    tool: dict[str, Any] = data.get("tool", {})
    d2: dict[str, Any] = tool.get("d2", {})
    return d2 or {}


def _detect_models(cwd: Path) -> str:
    if (cwd / "models.py").exists():
        return "models"
    if (cwd / "models" / "__init__.py").exists():
        return "models"
    raise FileNotFoundError(
        f"no [tool.d2] models setting and no models.py / models/ in {cwd}"
    )


def load_config(
    cwd: Path,
    *,
    migrations_dir_override: str | None = None,
    models_override: str | None = None,
) -> D2Config:
    """Load configuration for the migrations CLI."""
    tool_d2 = _read_tool_d2(cwd)

    migrations_dir_raw: str = (
        migrations_dir_override
        or cast(str | None, tool_d2.get("migrations_dir"))
        or "migrations"
    )
    models: str = (
        models_override
        or cast(str | None, tool_d2.get("models"))
        or _detect_models(cwd)
    )

    migrations_dir = cwd / migrations_dir_raw
    return D2Config(migrations_dir=migrations_dir, models=models)
