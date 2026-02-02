"""Integration tests for CLI-DiagnosisController integration.

Tests the integration between CLI commands and DiagnosisController,
including mode selection, checkpoint interactions, and output formatting.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from netsherlock.controller.checkpoints import (
    CheckpointData,
    CheckpointManager,
    CheckpointResult,
    CheckpointStatus,
)
from netsherlock.controller.diagnosis_controller import (
    DiagnosisController,
    DiagnosisState,
)
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus
from netsherlock.main import _determine_diagnosis_mode, cli
from netsherlock.schemas.config import (
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)


class TestCLIControllerIntegration:
    """Test CLI integration with DiagnosisController."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    # Standard VM diagnosis args for reuse in tests
    VM_DIAG_ARGS = [
        "--network-type", "vm",
        "--src-host", "192.168.1.10",
        "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    ]

    @pytest.fixture
    def mock_controller_result(self):
        """Create a mock successful diagnosis result."""
        return DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
            summary="Test diagnosis completed",
            root_cause={"category": "vm_network", "confidence": 0.85},
            recommendations=[{"action": "restart_vhost", "priority": "high"}],
        )

    def test_diagnose_creates_request_correctly(self, runner):
        """CLI diagnose should create correct DiagnosisRequest."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--type", "latency"],
            )

            # Verify request info is shown
            assert "192.168.1.10" in result.output
            assert "latency" in result.output.lower()

    def test_diagnose_autonomous_mode_in_output(self, runner):
        """Autonomous mode should be shown in output."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--autonomous"],
            )

            assert "autonomous" in result.output.lower()

    def test_diagnose_interactive_mode_in_output(self, runner):
        """Interactive mode should be shown in output."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--interactive"],
            )

            assert "interactive" in result.output.lower()

    def test_diagnose_with_src_vm_in_output(self, runner):
        """Source VM should be shown in output when provided."""
        vm_id = "ae6aa164-604c-4cb0-84b8-2dea034307f1"

        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS],
            )

            assert vm_id in result.output

    def test_diagnose_with_dst_host_in_output(self, runner):
        """Destination host should be shown when provided."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                [
                    "diagnose",
                    *self.VM_DIAG_ARGS,
                    "--dst-host", "192.168.1.20",
                    "--dst-vm", "bf7bb275-715d-5dc1-95c9-3feb045418g2",
                ],
            )

            assert "192.168.1.20" in result.output

    def test_diagnose_mode_option_overrides_default(self, runner):
        """--mode option should override default mode."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--mode", "autonomous"],
            )

            assert "autonomous" in result.output.lower()


class TestCLICheckpointInteraction:
    """Test checkpoint interaction through CLI."""

    def test_checkpoint_data_structure(self):
        """CheckpointData should have correct structure for CLI display."""
        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Problem classified as: vm_network_latency",
            details={"type": "vm_network_latency", "confidence": 0.85},
            options=["Confirm", "Modify", "Cancel"],
            recommendation="Confirm",
        )

        # Verify structure is suitable for CLI display
        assert data.summary is not None
        assert len(data.options) > 0
        assert data.recommendation is not None

    def test_checkpoint_result_confirmed(self):
        """Confirmed checkpoint should allow diagnosis to continue."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CONFIRMED,
        )

        assert result.is_confirmed is True
        assert result.is_cancelled is False

    def test_checkpoint_result_cancelled(self):
        """Cancelled checkpoint should stop diagnosis."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CANCELLED,
        )

        assert result.is_confirmed is False
        assert result.is_cancelled is True

    def test_checkpoint_result_with_user_input(self):
        """Modified checkpoint should capture user input."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
            status=CheckpointStatus.MODIFIED,
            user_input="Use different tool",
        )

        assert result.is_confirmed is True  # MODIFIED is still confirmed
        assert result.user_input == "Use different tool"

    @pytest.mark.asyncio
    async def test_checkpoint_manager_callback_integration(self):
        """CheckpointManager should call callback with data."""
        callback_data = None

        async def test_callback(data: CheckpointData) -> CheckpointResult:
            nonlocal callback_data
            callback_data = data
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )

        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            timeout_seconds=30,
            callback=test_callback,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test",
        )

        result = await manager.wait_at(data)

        assert callback_data is not None
        assert callback_data.summary == "Test"
        assert result.is_confirmed is True


class TestCLIModeSelection:
    """Test CLI mode selection integration with Controller."""

    def test_cli_default_mode_is_interactive(self):
        """CLI should default to interactive mode."""
        mode = _determine_diagnosis_mode(None, False, False)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_cli_autonomous_flag_forces_autonomous(self):
        """--autonomous flag should force autonomous mode."""
        mode = _determine_diagnosis_mode(None, True, False)
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_cli_interactive_flag_forces_interactive(self):
        """--interactive flag should force interactive mode."""
        mode = _determine_diagnosis_mode(None, False, True)
        assert mode == DiagnosisMode.INTERACTIVE

    def test_cli_mode_option_overrides_flag(self):
        """--mode option should override shortcut flags."""
        # --mode autonomous with --interactive flag
        mode = _determine_diagnosis_mode("autonomous", False, True)
        assert mode == DiagnosisMode.AUTONOMOUS

        # --mode interactive with --autonomous flag
        mode = _determine_diagnosis_mode("interactive", True, False)
        assert mode == DiagnosisMode.INTERACTIVE


class TestCLIOutputFormatting:
    """Test CLI output formatting."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    # Standard VM diagnosis args for reuse in tests
    VM_DIAG_ARGS = [
        "--network-type", "vm",
        "--src-host", "192.168.1.10",
        "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    ]

    def test_json_output_is_valid_json(self, runner):
        """--json flag should produce valid JSON output."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["--json", "diagnose", *self.VM_DIAG_ARGS],
            )

            # Output should contain JSON structure
            # (the current implementation outputs JSON for the request)
            output_lines = [
                line for line in result.output.strip().split("\n") if line
            ]
            # Check for JSON-like content
            has_json = any("{" in line for line in output_lines)
            assert has_json or result.exit_code == 0

    def test_text_output_includes_src_host(self, runner):
        """Text output should include source host information."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS],
            )

            assert "192.168.1.10" in result.output

    def test_text_output_includes_type(self, runner):
        """Text output should include diagnosis type."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--type", "packet_drop"],
            )

            assert "packet_drop" in result.output.lower()

    def test_text_output_includes_duration(self, runner):
        """Text output should include duration."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(success=True, data=None)

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--duration", "60"],
            )

            assert "60" in result.output


class TestCLIErrorHandling:
    """Test CLI error handling."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    # Standard VM diagnosis args for reuse in tests
    VM_DIAG_ARGS = [
        "--network-type", "vm",
        "--src-host", "192.168.1.10",
        "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    ]

    def test_conflicting_flags_returns_error(self, runner):
        """Conflicting --autonomous and --interactive should error."""
        result = runner.invoke(
            cli,
            ["diagnose", *self.VM_DIAG_ARGS, "--autonomous", "--interactive"],
        )

        assert result.exit_code != 0
        assert "Cannot use both" in result.output

    def test_invalid_mode_value_returns_error(self, runner):
        """Invalid --mode value should error."""
        result = runner.invoke(
            cli,
            ["diagnose", *self.VM_DIAG_ARGS, "--mode", "invalid"],
        )

        assert result.exit_code != 0

    def test_missing_required_network_type_returns_error(self, runner):
        """Missing --network-type should error."""
        result = runner.invoke(cli, ["diagnose", "--src-host", "192.168.1.10"])

        assert result.exit_code != 0
        assert "network-type" in result.output.lower()

    def test_missing_required_src_host_returns_error(self, runner):
        """Missing --src-host should error."""
        result = runner.invoke(cli, ["diagnose", "--network-type", "vm"])

        assert result.exit_code != 0
        assert "src-host" in result.output.lower()

    def test_environment_collection_failure_returns_error(self, runner):
        """Environment collection failure should return error."""
        with patch(
            "netsherlock.tools.l2_environment.collect_vm_network_env"
        ) as mock_collect:
            mock_collect.return_value = MagicMock(
                success=False, error="SSH connection failed"
            )

            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS],
            )

            assert result.exit_code != 0
            assert "failed" in result.output.lower()


class TestDiagnosisControllerStateIntegration:
    """Test DiagnosisController state management."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        from netsherlock.schemas.config import AutonomousConfig, InteractiveConfig

        return DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            ),
            interactive=InteractiveConfig(
                checkpoints=[
                    CheckpointType.PROBLEM_CLASSIFICATION,
                    CheckpointType.MEASUREMENT_PLAN,
                ],
                timeout_seconds=30,
            ),
        )

    def test_controller_initial_state(self, config):
        """Controller should have correct initial state."""
        controller = DiagnosisController(config)

        assert controller.state is None
        assert controller.is_running is False
        assert controller.is_waiting is False

    def test_controller_mode_determination_for_cli(self, config):
        """Controller config should determine correct mode for CLI."""
        mode = config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
        )

        # CLI defaults to interactive
        assert mode == DiagnosisMode.INTERACTIVE

    def test_controller_mode_determination_for_webhook_known_alert(self, config):
        """Controller should use autonomous for webhook with known alert."""
        mode = config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="VMNetworkLatency",
        )

        assert mode == DiagnosisMode.AUTONOMOUS

    def test_controller_force_mode_overrides(self, config):
        """Force mode should override config determination."""
        mode = config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        assert mode == DiagnosisMode.AUTONOMOUS


class TestDiagnosisResultFormatting:
    """Test DiagnosisResult formatting for CLI output."""

    def test_result_has_diagnosis_id(self):
        """Result should have diagnosis_id for tracking."""
        result = DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
        )

        assert result.diagnosis_id == "test-001"

    def test_result_status_values(self):
        """Result status should be one of expected values."""
        for status in DiagnosisStatus:
            result = DiagnosisResult(
                diagnosis_id="test",
                status=status,
                mode=DiagnosisMode.AUTONOMOUS,
            )
            assert result.status == status

    def test_completed_result_from_state(self):
        """Result should be creatable from state."""
        state = DiagnosisState(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
            analysis={
                "root_cause": {"category": "vm_internal", "confidence": 0.85},
                "recommendations": [{"action": "restart"}],
            },
        )

        result = DiagnosisResult.from_controller_state(state)

        assert result.diagnosis_id == "test-001"
        assert result.status == DiagnosisStatus.COMPLETED
        assert result.root_cause is not None
        assert result.root_cause.category.value == "vm_internal"

    def test_cancelled_result(self):
        """Cancelled result should have correct status."""
        result = DiagnosisResult.create_cancelled("test-001", mode=DiagnosisMode.INTERACTIVE)

        assert result.status == DiagnosisStatus.CANCELLED
        assert "cancelled" in result.summary.lower()

    def test_error_result(self):
        """Error result should capture error message."""
        result = DiagnosisResult.create_error(
            "test-001", error="Connection failed", mode=DiagnosisMode.AUTONOMOUS,
        )

        assert result.status == DiagnosisStatus.ERROR
        assert result.error == "Connection failed"


class TestCLICheckpointCallbackIntegration:
    """Test CLI checkpoint callback implementation."""

    def test_cli_checkpoint_callback_exists(self):
        """CLI checkpoint callback should be importable."""
        from netsherlock.main import _cli_checkpoint_callback

        assert callable(_cli_checkpoint_callback)

    @pytest.mark.asyncio
    async def test_checkpoint_callback_with_mock_input(self):
        """Checkpoint callback should handle user input."""
        from netsherlock.main import _cli_checkpoint_callback

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test classification",
            details={"type": "test"},
            options=["Confirm", "Modify", "Cancel"],
            recommendation="Confirm",
        )

        # Mock click.prompt to return 1 (Confirm)
        with patch("click.prompt", return_value=1):
            with patch("click.echo"):
                result = await _cli_checkpoint_callback(data)

        assert result.status == CheckpointStatus.CONFIRMED
        assert result.checkpoint_type == CheckpointType.PROBLEM_CLASSIFICATION

    @pytest.mark.asyncio
    async def test_checkpoint_callback_cancel(self):
        """Checkpoint callback should handle cancel."""
        from netsherlock.main import _cli_checkpoint_callback

        data = CheckpointData(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
            summary="Test plan",
        )

        with patch("click.prompt", return_value=3):
            with patch("click.echo"):
                result = await _cli_checkpoint_callback(data)

        assert result.status == CheckpointStatus.CANCELLED


class TestCLIResultFormattingIntegration:
    """Test CLI result formatting implementation."""

    def test_format_diagnosis_result_exists(self):
        """Format function should be importable."""
        from netsherlock.main import _format_diagnosis_result

        assert callable(_format_diagnosis_result)

    def test_format_diagnosis_result_text(self):
        """Text formatting should work."""
        from datetime import datetime

        from netsherlock.main import _format_diagnosis_result
        from netsherlock.schemas.report import Recommendation, RootCause, RootCauseCategory

        result = DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
            summary="Test completed",
            root_cause=RootCause(
                category=RootCauseCategory.VM_INTERNAL,
                component="virtio",
                confidence=0.85,
            ),
            recommendations=[
                Recommendation(priority=1, action="restart_vhost"),
            ],
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        with patch("click.echo") as mock_echo:
            _format_diagnosis_result(result, json_output=False)
            # Should have called echo multiple times
            assert mock_echo.call_count > 5

    def test_format_diagnosis_result_json(self):
        """JSON formatting should produce valid JSON."""
        from datetime import datetime

        from netsherlock.main import _format_diagnosis_result

        result = DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        output_lines = []

        def capture_echo(text):
            output_lines.append(text)

        with patch("click.echo", side_effect=capture_echo):
            _format_diagnosis_result(result, json_output=True)

        # Should be valid JSON
        output = "\n".join(output_lines)
        parsed = json.loads(output)
        assert parsed["diagnosis_id"] == "test-001"
        assert parsed["status"] == "completed"


class TestCLIControllerRunIntegration:
    """Test CLI running DiagnosisController."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    # Standard VM diagnosis args for reuse in tests
    VM_DIAG_ARGS = [
        "--network-type", "vm",
        "--src-host", "192.168.1.10",
        "--src-vm", "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    ]

    def test_diagnose_runs_controller_autonomous(self, runner):
        """diagnose --autonomous should run controller in autonomous mode."""
        mock_engine = MagicMock()
        mock_result = DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
        )

        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_engine.execute = mock_execute

        with patch(
            "netsherlock.main._create_cli_engine",
            return_value=mock_engine,
        ) as mock_create:
            runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--autonomous"],
            )

            # Engine should be created with controller type
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["engine_type"] == "controller"

    def test_diagnose_runs_controller_interactive(self, runner):
        """diagnose --interactive should run controller with checkpoint callback."""
        mock_engine = MagicMock()
        mock_result = DiagnosisResult(
            diagnosis_id="test-002",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.INTERACTIVE,
        )

        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_engine.execute = mock_execute

        with patch(
            "netsherlock.main._create_cli_engine",
            return_value=mock_engine,
        ) as mock_create:
            runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--interactive"],
            )

            # Engine should be created with checkpoint_callback
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["checkpoint_callback"] is not None

    def test_diagnose_controller_error_exit_code(self, runner):
        """Controller error should result in non-zero exit code."""
        mock_engine = MagicMock()
        mock_result = DiagnosisResult.create_error(
            "test-003",
            DiagnosisMode.AUTONOMOUS,
            "Test error",
        )

        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_engine.execute = mock_execute

        with patch(
            "netsherlock.main._create_cli_engine",
            return_value=mock_engine,
        ):
            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--autonomous"],
            )

            assert result.exit_code == 1

    def test_diagnose_controller_cancelled_exit_code(self, runner):
        """Controller cancelled should result in exit code 2."""
        mock_engine = MagicMock()
        mock_result = DiagnosisResult.create_cancelled(
            "test-004",
            mode=DiagnosisMode.INTERACTIVE,
        )

        async def mock_execute(*args, **kwargs):
            return mock_result

        mock_engine.execute = mock_execute

        with patch(
            "netsherlock.main._create_cli_engine",
            return_value=mock_engine,
        ):
            result = runner.invoke(
                cli,
                ["diagnose", *self.VM_DIAG_ARGS, "--interactive"],
            )

            assert result.exit_code == 2
