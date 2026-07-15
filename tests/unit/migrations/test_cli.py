"""Unit tests for the migrations CLI helpers (make/check, no DB)."""

import sys
from pathlib import Path

import pytest

from d2.migrations.__main__ import cmd_check, cmd_make


def _write_models(tmp_path: Path, source: str) -> None:
    (tmp_path / "models.py").write_text(source)
    (tmp_path / "pyproject.toml").write_text("[tool.d2]\n")


MODEL_SIMPLE = """
from d2 import db
from d2.schema import Table, Field, PrimaryKey
from d2.model import field

class CliWidget(Table):
    id: PrimaryKey[int] = field(default=db.serial())
    label: Field[str]
"""


class TestCmdMake:
    def test_make_empty_diff_prints_message_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "models.py").write_text("")
        (tmp_path / "pyproject.toml").write_text("[tool.d2]\n")
        (tmp_path / "migrations").mkdir()

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_make(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc == 0
        assert capsys.readouterr().out == "No changes detected.\n"
        assert list((tmp_path / "migrations").glob("*.py")) == []

    def test_make_non_empty_writes_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_models(tmp_path, MODEL_SIMPLE)
        (tmp_path / "migrations").mkdir()

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_make(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc == 0
        files = list((tmp_path / "migrations").glob("*.py"))
        assert len(files) == 1
        assert files[0].name == "0001_create_cli_widgets.py"


class TestCmdCheck:
    def test_check_in_sync_silent_and_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "models.py").write_text("")
        (tmp_path / "pyproject.toml").write_text("[tool.d2]\n")
        (tmp_path / "migrations").mkdir()

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_check(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_check_drift_nonzero_with_file_and_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_models(tmp_path, MODEL_SIMPLE)
        (tmp_path / "migrations").mkdir()

        sys.path.insert(0, str(tmp_path))
        try:
            rc = cmd_check(cwd=tmp_path)
        finally:
            sys.path.remove(str(tmp_path))

        assert rc != 0
        out = capsys.readouterr().out
        assert out == f"{tmp_path / 'models.py'}:1: schema drift detected\n"
