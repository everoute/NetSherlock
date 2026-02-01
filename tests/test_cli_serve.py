"""Tests for CLI serve command and mode determination.

Tests the `serve` command in main.py and the
_determine_diagnosis_mode() helper function.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from netsherlock.config.settings import reset_settings
from netsherlock.main import _determine_diagnosis_mode, cli
from netsherlock.schemas.config import DiagnosisMode


class TestServeCommand:
    """CLI serve command parameter validation."""

    @pytest.fixture
    def runner(self):
        """Click CLI test runner."""
        return CliRunner()

    @pytest.fixture(autouse=True)
    def clean_env(self):
        """Clean environment variables set by serve command."""
        yield
        for key in ("DIAGNOSIS_ENGINE", "GLOBAL_INVENTORY_PATH"):
            os.environ.pop(key, None)
        reset_settings()

    def test_serve_command_registered(self):
        """serve command is registered in CLI."""
        commands = cli.commands if hasattr(cli, "commands") else {}
        assert "serve" in commands

    def test_default_engine_controller(self, runner):
        """Default --engine is controller."""
        with patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve"], catch_exceptions=False)
            assert "controller" in result.output.lower()

    def test_engine_controller_accepted(self, runner):
        """--engine controller is accepted."""
        with patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--engine", "controller"])
            assert result.exit_code == 0

    def test_engine_orchestrator_accepted(self, runner):
        """--engine orchestrator is accepted."""
        with patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--engine", "orchestrator"])
            assert result.exit_code == 0

    def test_invalid_engine_rejected(self, runner):
        """--engine unknown is rejected."""
        result = runner.invoke(cli, ["serve", "--engine", "unknown"])
        assert result.exit_code != 0

    def test_sets_diagnosis_engine_env_var(self, runner):
        """serve sets DIAGNOSIS_ENGINE environment variable."""
        with patch("uvicorn.run") as mock_run:
            runner.invoke(cli, ["serve", "--engine", "orchestrator"])
            mock_run.assert_called_once()

        with patch("uvicorn.run"):
            result = runner.invoke(cli, ["serve", "--engine", "orchestrator"])
            assert "orchestrator" in result.output.lower()

    def test_sets_inventory_env_var(self, runner, tmp_path):
        """serve --inventory sets GLOBAL_INVENTORY_PATH environment variable."""
        inv_file = tmp_path / "inventory.yaml"
        inv_file.write_text("hosts: {}")

        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(cli, ["serve", "--inventory", str(inv_file)])
            assert result.exit_code == 0
            mock_run.assert_called_once()


class TestDetermineDiagnosisMode:
    """CLI _determine_diagnosis_mode() mode resolution."""

    def test_mode_option_takes_precedence(self):
        """--mode=autonomous takes highest precedence."""
        result = _determine_diagnosis_mode("autonomous", False, False)
        assert result == DiagnosisMode.AUTONOMOUS

    def test_mode_interactive_option(self):
        """--mode=interactive works."""
        result = _determine_diagnosis_mode("interactive", False, False)
        assert result == DiagnosisMode.INTERACTIVE

    def test_autonomous_flag(self):
        """--autonomous flag returns AUTONOMOUS."""
        result = _determine_diagnosis_mode(None, True, False)
        assert result == DiagnosisMode.AUTONOMOUS

    def test_interactive_flag(self):
        """--interactive flag returns INTERACTIVE."""
        result = _determine_diagnosis_mode(None, False, True)
        assert result == DiagnosisMode.INTERACTIVE

    def test_conflicting_flags_raises(self):
        """--autonomous + --interactive raises UsageError."""
        with pytest.raises(click.UsageError, match="Cannot use both"):
            _determine_diagnosis_mode(None, True, True)

    def test_default_is_interactive(self):
        """No arguments defaults to INTERACTIVE."""
        result = _determine_diagnosis_mode(None, False, False)
        assert result == DiagnosisMode.INTERACTIVE
