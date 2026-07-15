"""Unit tests for migrations config loader."""

from pathlib import Path

from d2.migrations.config import D2Config, load_config


PYPROJECT_FULL = """
[tool.d2]
migrations_dir = "mymigs"
models = "myapp.models"
"""

PYPROJECT_EMPTY = """
[project]
name = "x"
"""


class TestLoadConfig:
    def test_reads_tool_d2_section(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_FULL)
        cfg = load_config(tmp_path)
        assert cfg == D2Config(
            migrations_dir=tmp_path / "mymigs",
            models="myapp.models",
        )

    def test_falls_back_to_models_py_at_cwd(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_EMPTY)
        (tmp_path / "models.py").write_text("")
        cfg = load_config(tmp_path)
        assert cfg.models == "models"
        assert cfg.migrations_dir == tmp_path / "migrations"

    def test_falls_back_to_models_package_at_cwd(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_EMPTY)
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "__init__.py").write_text("")
        cfg = load_config(tmp_path)
        assert cfg.models == "models"

    def test_cli_overrides_win(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(PYPROJECT_FULL)
        cfg = load_config(
            tmp_path,
            migrations_dir_override="alt",
            models_override="other.models",
        )
        assert cfg.migrations_dir == tmp_path / "alt"
        assert cfg.models == "other.models"
