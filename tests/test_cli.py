"""Tests for the Anythink CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from anythink.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "anythink" in result.output.lower()


def test_keys_help() -> None:
    result = runner.invoke(app, ["keys", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_model_help() -> None:
    result = runner.invoke(app, ["model", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_keys_list_stub() -> None:
    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0


def test_model_list_stub() -> None:
    result = runner.invoke(app, ["model", "list"])
    assert result.exit_code == 0
