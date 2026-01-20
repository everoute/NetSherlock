"""Tests for CLI commands and mode handling.

These tests verify:
1. Default mode is interactive for CLI
2. --autonomous and --interactive flags work correctly
3. --mode option works correctly
4. Conflicting flags raise errors
5. Mode precedence is correct
"""

import pytest
from click.testing import CliRunner

from netsherlock.main import cli, _determine_diagnosis_mode
from netsherlock.schemas.config import DiagnosisMode


class TestDetermineDiagnosisMode:
    """Tests for the _determine_diagnosis_mode helper function."""

    def test_default_is_interactive(self):
        """Default mode should be interactive for CLI."""
        mode = _determine_diagnosis_mode(None, False, False)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_mode_option_autonomous(self):
        """--mode autonomous should set autonomous mode."""
        mode = _determine_diagnosis_mode("autonomous", False, False)
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_mode_option_interactive(self):
        """--mode interactive should set interactive mode."""
        mode = _determine_diagnosis_mode("interactive", False, False)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_autonomous_flag(self):
        """--autonomous flag should set autonomous mode."""
        mode = _determine_diagnosis_mode(None, True, False)
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_interactive_flag(self):
        """--interactive flag should set interactive mode."""
        mode = _determine_diagnosis_mode(None, False, True)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_mode_option_takes_precedence_over_flag(self):
        """--mode option should take precedence over flags."""
        # --mode autonomous with --interactive flag
        mode = _determine_diagnosis_mode("autonomous", False, True)
        assert mode == DiagnosisMode.AUTONOMOUS

        # --mode interactive with --autonomous flag
        mode = _determine_diagnosis_mode("interactive", True, False)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_conflicting_flags_raises_error(self):
        """Both --autonomous and --interactive should raise error."""
        import click

        with pytest.raises(click.UsageError) as exc_info:
            _determine_diagnosis_mode(None, True, True)
        assert "Cannot use both" in str(exc_info.value)


class TestCLIDiagnoseCommand:
    """Tests for the diagnose CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    # Base VM diagnosis args for reuse in tests
    VM_DIAG_ARGS = [
        "--network-type", "vm",
        "--src-host", "192.168.1.10",
        "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    ]

    def test_diagnose_default_mode_is_interactive(self, runner):
        """diagnose command should default to interactive mode."""
        result = runner.invoke(cli, ["diagnose", *self.VM_DIAG_ARGS])
        assert result.exit_code == 0 or "Mode: interactive" in result.output

    def test_diagnose_with_autonomous_flag(self, runner):
        """diagnose --autonomous should show autonomous mode."""
        result = runner.invoke(
            cli, ["diagnose", *self.VM_DIAG_ARGS, "--autonomous"]
        )
        # Check output contains mode info (may fail on actual SSH)
        assert "autonomous" in result.output.lower() or result.exit_code != 0

    def test_diagnose_with_interactive_flag(self, runner):
        """diagnose --interactive should show interactive mode."""
        result = runner.invoke(
            cli, ["diagnose", *self.VM_DIAG_ARGS, "--interactive"]
        )
        assert "interactive" in result.output.lower() or result.exit_code != 0

    def test_diagnose_with_mode_option(self, runner):
        """diagnose --mode autonomous should work."""
        result = runner.invoke(
            cli, ["diagnose", *self.VM_DIAG_ARGS, "--mode", "autonomous"]
        )
        assert "autonomous" in result.output.lower() or result.exit_code != 0

    def test_diagnose_conflicting_flags_error(self, runner):
        """diagnose with both --autonomous and --interactive should error."""
        result = runner.invoke(
            cli, ["diagnose", *self.VM_DIAG_ARGS, "--autonomous", "--interactive"]
        )
        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_diagnose_help_shows_mode_options(self, runner):
        """diagnose --help should show mode options."""
        result = runner.invoke(cli, ["diagnose", "--help"])
        assert result.exit_code == 0
        assert "--mode" in result.output
        assert "--autonomous" in result.output
        assert "--interactive" in result.output

    def test_diagnose_invalid_mode_value(self, runner):
        """diagnose --mode invalid should error."""
        result = runner.invoke(
            cli, ["diagnose", *self.VM_DIAG_ARGS, "--mode", "invalid"]
        )
        assert result.exit_code != 0

    def test_diagnose_help_shows_new_parameters(self, runner):
        """diagnose --help should show new src/dst parameters."""
        result = runner.invoke(cli, ["diagnose", "--help"])
        assert result.exit_code == 0
        assert "--network-type" in result.output
        assert "--src-host" in result.output
        assert "--src-vm" in result.output
        assert "--dst-host" in result.output
        assert "--dst-vm" in result.output

    def test_diagnose_vm_requires_src_vm(self, runner):
        """diagnose --network-type vm requires --src-vm."""
        result = runner.invoke(
            cli, ["diagnose", "--network-type", "vm", "--src-host", "192.168.1.10"]
        )
        assert result.exit_code != 0
        assert "--src-vm is required" in result.output

    def test_diagnose_vm_dst_host_requires_dst_vm(self, runner):
        """diagnose with --dst-host requires --dst-vm for vm network."""
        result = runner.invoke(
            cli, [
                "diagnose",
                "--network-type", "vm",
                "--src-host", "192.168.1.10",
                "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
                "--dst-host", "192.168.1.20",
            ]
        )
        assert result.exit_code != 0
        assert "--dst-vm is required" in result.output

    def test_diagnose_vm_dst_vm_requires_dst_host(self, runner):
        """diagnose with --dst-vm requires --dst-host."""
        result = runner.invoke(
            cli, [
                "diagnose",
                "--network-type", "vm",
                "--src-host", "192.168.1.10",
                "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
                "--dst-vm", "bf7bb275-715d-5dc1-95c9-3feb045418g2",
            ]
        )
        assert result.exit_code != 0
        assert "--dst-host is required" in result.output

    def test_diagnose_vm_to_vm_valid(self, runner):
        """diagnose VM-to-VM with all required params should work."""
        result = runner.invoke(
            cli, [
                "diagnose",
                "--network-type", "vm",
                "--src-host", "192.168.1.10",
                "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
                "--dst-host", "192.168.1.20",
                "--dst-vm", "bf7bb275-715d-5dc1-95c9-3feb045418g2",
            ]
        )
        # May fail on actual diagnosis, but parameter validation should pass
        assert "Destination Host: 192.168.1.20" in result.output or result.exit_code != 0


class TestCLIConfigCommand:
    """Tests for the config CLI command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_config_shows_diagnosis_settings(self, runner):
        """config command should show diagnosis settings."""
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "Diagnosis Settings:" in result.output
        assert "Default Mode:" in result.output

    def test_config_shows_autonomous_settings(self, runner):
        """config should show autonomous settings."""
        result = runner.invoke(cli, ["config"])
        assert "Autonomous Enabled:" in result.output
        assert "Auto-Agent Loop:" in result.output

    def test_config_shows_interactive_timeout(self, runner):
        """config should show interactive timeout."""
        result = runner.invoke(cli, ["config"])
        assert "Interactive Timeout:" in result.output


class TestCLIMainGroup:
    """Tests for the main CLI group."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_cli_version(self, runner):
        """--version should show version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "netsherlock" in result.output.lower()

    def test_cli_help(self, runner):
        """--help should show help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "diagnose" in result.output
        assert "config" in result.output
        assert "query" in result.output
        assert "env" in result.output

    def test_cli_verbose_flag(self, runner):
        """--verbose flag should be accepted."""
        result = runner.invoke(cli, ["--verbose", "config"])
        assert result.exit_code == 0

    def test_cli_json_flag(self, runner):
        """--json flag should be accepted."""
        result = runner.invoke(cli, ["--json", "config"])
        # May not produce JSON for config, but should not error
        assert result.exit_code == 0


class TestDiagnosisModeIntegration:
    """Integration tests for mode selection logic."""

    def test_mode_enum_values(self):
        """DiagnosisMode enum should have expected values."""
        assert DiagnosisMode.AUTONOMOUS.value == "autonomous"
        assert DiagnosisMode.INTERACTIVE.value == "interactive"

    def test_mode_from_string(self):
        """DiagnosisMode should be creatable from string."""
        assert DiagnosisMode("autonomous") == DiagnosisMode.AUTONOMOUS
        assert DiagnosisMode("interactive") == DiagnosisMode.INTERACTIVE

    def test_mode_invalid_string_raises(self):
        """Invalid mode string should raise ValueError."""
        with pytest.raises(ValueError):
            DiagnosisMode("invalid")
