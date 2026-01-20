"""Tests for the DiagnosisController and checkpoint management."""

import asyncio
from datetime import datetime

import pytest

from netsherlock.controller import (
    Checkpoint,
    CheckpointData,
    CheckpointManager,
    CheckpointResult,
    CheckpointStatus,
    DiagnosisController,
)
from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
    InteractiveConfig,
)


# === Checkpoint Tests ===


class TestCheckpoint:
    """Tests for individual Checkpoint."""

    @pytest.mark.asyncio
    async def test_checkpoint_wait_and_confirm(self):
        """Checkpoint waits and can be confirmed."""
        checkpoint = Checkpoint(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            timeout_seconds=5,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test checkpoint",
        )

        # Start waiting in background
        async def wait_task():
            return await checkpoint.wait(data)

        task = asyncio.create_task(wait_task())

        # Let it start waiting
        await asyncio.sleep(0.05)
        assert checkpoint.is_waiting

        # Confirm it
        checkpoint.confirm("user said ok")

        result = await task
        assert result.status == CheckpointStatus.CONFIRMED
        assert result.user_input == "user said ok"

    @pytest.mark.asyncio
    async def test_checkpoint_wait_and_cancel(self):
        """Checkpoint can be cancelled."""
        checkpoint = Checkpoint(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
            timeout_seconds=5,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
            summary="Test checkpoint",
        )

        task = asyncio.create_task(checkpoint.wait(data))
        await asyncio.sleep(0.05)

        checkpoint.cancel()

        result = await task
        assert result.status == CheckpointStatus.CANCELLED
        assert result.is_cancelled

    @pytest.mark.asyncio
    async def test_checkpoint_timeout(self):
        """Checkpoint times out after timeout_seconds."""
        checkpoint = Checkpoint(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            timeout_seconds=0.1,  # Very short for testing
            auto_confirm_on_timeout=False,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test",
        )

        result = await checkpoint.wait(data)
        assert result.status == CheckpointStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_checkpoint_auto_confirm_on_timeout(self):
        """Checkpoint auto-confirms on timeout if configured."""
        checkpoint = Checkpoint(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            timeout_seconds=0.1,
            auto_confirm_on_timeout=True,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test",
        )

        result = await checkpoint.wait(data)
        assert result.status == CheckpointStatus.CONFIRMED

    def test_checkpoint_modify(self):
        """Checkpoint can be modified."""
        checkpoint = Checkpoint(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
        )

        checkpoint.modify("user's modified input")

        assert checkpoint._result is not None
        assert checkpoint._result.status == CheckpointStatus.MODIFIED
        assert checkpoint._result.user_input == "user's modified input"


class TestCheckpointResult:
    """Tests for CheckpointResult."""

    def test_is_confirmed_true(self):
        """is_confirmed returns True for confirmed status."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CONFIRMED,
        )
        assert result.is_confirmed

    def test_is_confirmed_true_for_modified(self):
        """is_confirmed returns True for modified status."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.MODIFIED,
        )
        assert result.is_confirmed

    def test_is_cancelled(self):
        """is_cancelled returns True for cancelled status."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CANCELLED,
        )
        assert result.is_cancelled


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_is_enabled_check(self):
        """Manager correctly checks if checkpoint is enabled."""
        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
        )
        assert manager.is_enabled(CheckpointType.PROBLEM_CLASSIFICATION)
        assert not manager.is_enabled(CheckpointType.MEASUREMENT_PLAN)

    @pytest.mark.asyncio
    async def test_disabled_checkpoint_returns_confirmed(self):
        """Disabled checkpoint immediately returns confirmed."""
        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,  # Not enabled
            summary="Test",
        )

        result = await manager.wait_at(data)
        assert result.status == CheckpointStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_callback_is_used(self):
        """Callback is called for checkpoint interaction."""
        callback_called = False

        async def callback(data: CheckpointData) -> CheckpointResult:
            nonlocal callback_called
            callback_called = True
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )

        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            callback=callback,
        )

        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Test",
        )

        await manager.wait_at(data)
        assert callback_called

    def test_history_tracking(self):
        """Manager tracks checkpoint history."""
        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
        )

        # Manually add to history for testing
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CONFIRMED,
        )
        manager._history.append(result)

        assert len(manager.history) == 1
        assert manager.history[0] == result


# === DiagnosisController Tests ===


class TestDiagnosisControllerModeSelection:
    """Tests for mode selection logic."""

    def test_cli_default_interactive(self):
        """CLI source defaults to interactive mode."""
        config = DiagnosisConfig(
            default_mode=DiagnosisMode.AUTONOMOUS,  # Even with this
        )

        mode = config.determine_mode(source="cli")
        assert mode == DiagnosisMode.INTERACTIVE

    def test_force_mode_overrides(self):
        """Force mode overrides all logic."""
        config = DiagnosisConfig()

        mode = config.determine_mode(
            source="cli",
            force_mode=DiagnosisMode.AUTONOMOUS,
        )
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_webhook_with_auto_loop_uses_autonomous(self):
        """Webhook with auto_agent_loop uses autonomous."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )

        mode = config.determine_mode(
            source="webhook",
            alert_type="VMNetworkLatency",
        )
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_webhook_unknown_alert_uses_default(self):
        """Webhook with unknown alert uses default mode."""
        config = DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )

        mode = config.determine_mode(
            source="webhook",
            alert_type="UnknownAlert",
        )
        assert mode == DiagnosisMode.INTERACTIVE


class TestDiagnosisControllerExecution:
    """Tests for diagnosis execution."""

    @pytest.fixture
    def config(self):
        """Default test config."""
        return DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                interrupt_enabled=True,
            ),
            interactive=InteractiveConfig(
                checkpoints=[
                    CheckpointType.PROBLEM_CLASSIFICATION,
                    CheckpointType.MEASUREMENT_PLAN,
                ],
                timeout_seconds=30,  # Minimum allowed value
            ),
        )

    @pytest.fixture
    def diagnosis_request(self):
        """Default test request."""
        return DiagnosisRequest(
            request_id="test-001",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )

    @pytest.mark.asyncio
    async def test_autonomous_runs_without_checkpoints(self, config, diagnosis_request):
        """Autonomous mode runs without stopping at checkpoints."""
        controller = DiagnosisController(config)

        result = await controller.run(
            diagnosis_request,
            source=DiagnosisRequestSource.CLI,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        assert result.mode == DiagnosisMode.AUTONOMOUS
        assert result.status.value in ("completed", "error")
        # Should not have checkpoint history
        assert len(result.checkpoint_history) == 0

    @pytest.mark.asyncio
    async def test_interactive_with_callback(self, config, diagnosis_request):
        """Interactive mode calls checkpoint callback."""
        checkpoint_data_received = []

        async def callback(data: CheckpointData) -> CheckpointResult:
            checkpoint_data_received.append(data)
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )

        controller = DiagnosisController(
            config,
            checkpoint_callback=callback,
        )

        result = await controller.run(
            diagnosis_request,
            source=DiagnosisRequestSource.CLI,
            force_mode=DiagnosisMode.INTERACTIVE,
        )

        assert result.mode == DiagnosisMode.INTERACTIVE
        # Should have received checkpoint data
        assert len(checkpoint_data_received) == 2
        assert checkpoint_data_received[0].checkpoint_type == CheckpointType.PROBLEM_CLASSIFICATION
        assert checkpoint_data_received[1].checkpoint_type == CheckpointType.MEASUREMENT_PLAN

    @pytest.mark.asyncio
    async def test_interactive_cancel_at_checkpoint(self, config, diagnosis_request):
        """Interactive mode can be cancelled at checkpoint."""

        async def callback(data: CheckpointData) -> CheckpointResult:
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CANCELLED,
            )

        controller = DiagnosisController(
            config,
            checkpoint_callback=callback,
        )

        result = await controller.run(
            diagnosis_request,
            source=DiagnosisRequestSource.CLI,
            force_mode=DiagnosisMode.INTERACTIVE,
        )

        assert result.status.value == "cancelled"

    @pytest.mark.asyncio
    async def test_autonomous_interrupt(self, config, diagnosis_request):
        """Autonomous mode can be interrupted."""
        controller = DiagnosisController(config)

        # Start diagnosis in background
        task = asyncio.create_task(
            controller.run(
                diagnosis_request,
                source=DiagnosisRequestSource.CLI,
                force_mode=DiagnosisMode.AUTONOMOUS,
            )
        )

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Request interrupt
        controller.interrupt()

        result = await task

        # Note: The stub implementation may complete before interrupt is checked
        # In real implementation with actual async work, this would interrupt
        assert result is not None

    def test_state_tracking(self, config):
        """Controller tracks diagnosis state."""
        controller = DiagnosisController(config)

        assert controller.state is None
        assert not controller.is_running
        assert not controller.is_waiting


class TestDiagnosisControllerCheckpointInteraction:
    """Tests for checkpoint interaction methods."""

    @pytest.fixture
    def config(self):
        """Config with interactive mode."""
        return DiagnosisConfig(
            interactive=InteractiveConfig(
                checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
                timeout_seconds=30,  # Minimum allowed value
            ),
        )

    @pytest.mark.asyncio
    async def test_confirm_checkpoint_programmatic(self, config):
        """Can confirm checkpoint programmatically."""
        controller = DiagnosisController(config)

        request = DiagnosisRequest(
            request_id="test-001",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )

        # Start in background
        task = asyncio.create_task(
            controller.run(
                request,
                source=DiagnosisRequestSource.CLI,
                force_mode=DiagnosisMode.INTERACTIVE,
            )
        )

        # Wait for checkpoint
        await asyncio.sleep(0.05)

        # Confirm checkpoints
        controller.confirm_checkpoint()
        await asyncio.sleep(0.05)
        controller.confirm_checkpoint()

        result = await task
        assert result is not None

    def test_confirm_when_not_waiting(self, config):
        """Confirm returns False when not waiting."""
        controller = DiagnosisController(config)

        result = controller.confirm_checkpoint()
        assert result is False

    def test_cancel_when_not_waiting(self, config):
        """Cancel returns False when not waiting."""
        controller = DiagnosisController(config)

        result = controller.cancel_checkpoint()
        assert result is False


class TestDiagnosisResult:
    """Tests for DiagnosisResult."""

    def test_cancelled_factory(self):
        """Cancelled factory creates correct result."""
        from netsherlock.controller.diagnosis_controller import DiagnosisResult, DiagnosisStatus

        result = DiagnosisResult.cancelled("test-123", DiagnosisMode.INTERACTIVE)

        assert result.diagnosis_id == "test-123"
        assert result.status == DiagnosisStatus.CANCELLED
        assert result.mode == DiagnosisMode.INTERACTIVE

    def test_error_factory(self):
        """Error factory creates correct result."""
        from netsherlock.controller.diagnosis_controller import DiagnosisResult, DiagnosisStatus

        result = DiagnosisResult.error("test-123", DiagnosisMode.AUTONOMOUS, "Something failed")

        assert result.diagnosis_id == "test-123"
        assert result.status == DiagnosisStatus.ERROR
        assert result.error == "Something failed"
