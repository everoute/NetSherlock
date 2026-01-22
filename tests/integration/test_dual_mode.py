"""Integration tests for dual-mode control (Autonomous/Interactive).

Tests mode selection logic, checkpoint behavior, and mode switching.
"""


import pytest

from netsherlock.controller.checkpoints import (
    CheckpointData,
    CheckpointManager,
    CheckpointResult,
    CheckpointStatus,
)
from netsherlock.controller.diagnosis_controller import DiagnosisController
from netsherlock.schemas.config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
    InteractiveConfig,
)


class TestModeSelectionIntegration:
    """Test mode selection logic across different scenarios."""

    def test_cli_default_is_interactive(self, interactive_config):
        """CLI source should default to interactive mode."""
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
        )
        assert mode == DiagnosisMode.INTERACTIVE

    def test_cli_with_known_alert_still_interactive(self, interactive_config):
        """CLI with known alert type should still use interactive (CLI default)."""
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type="VMNetworkLatency",
        )
        # CLI always defaults to interactive unless forced
        assert mode == DiagnosisMode.INTERACTIVE

    def test_webhook_known_alert_with_auto_loop_is_autonomous(self, autonomous_config):
        """Webhook + known alert + auto_agent_loop should use autonomous."""
        mode = autonomous_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="VMNetworkLatency",
        )
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_webhook_unknown_alert_uses_default_mode(self, autonomous_config):
        """Webhook with unknown alert should use default mode."""
        mode = autonomous_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="UnknownAlertType",
        )
        # Unknown alert type doesn't auto-trigger autonomous, falls back to default_mode
        # The config's default_mode is used
        assert mode == autonomous_config.default_mode

    def test_webhook_no_auto_loop_is_interactive(self, interactive_config):
        """Webhook without auto_agent_loop should use interactive."""
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="VMNetworkLatency",
        )
        # auto_agent_loop is false in interactive_config
        assert mode == DiagnosisMode.INTERACTIVE

    def test_force_mode_overrides_all(self, interactive_config):
        """Force mode should override all other logic."""
        # Force autonomous from CLI (which normally defaults to interactive)
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )
        assert mode == DiagnosisMode.AUTONOMOUS

        # Force interactive from webhook with known alert
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="VMNetworkLatency",
            force_mode=DiagnosisMode.INTERACTIVE,
        )
        assert mode == DiagnosisMode.INTERACTIVE


class TestAutonomousModeIntegration:
    """Test autonomous mode behavior."""

    def test_autonomous_config_has_auto_loop_enabled(self, autonomous_config):
        """Autonomous config should have auto_agent_loop enabled."""
        assert autonomous_config.autonomous.auto_agent_loop is True

    def test_autonomous_known_alert_triggers_auto_loop(self, autonomous_config):
        """Known alert type should trigger auto agent loop."""
        # VMNetworkLatency is in known_alert_types
        is_allowed = autonomous_config.is_autonomous_allowed("VMNetworkLatency")
        assert is_allowed is True

    def test_autonomous_unknown_alert_no_auto_loop(self, autonomous_config):
        """Unknown alert type should not trigger auto agent loop."""
        # CustomAlert is not in known_alert_types
        is_allowed = autonomous_config.is_autonomous_allowed("CustomAlert")
        assert is_allowed is False

    def test_autonomous_controller_no_checkpoint_manager_for_autonomous(self, autonomous_config):
        """Autonomous mode should not initialize checkpoint manager."""
        controller = DiagnosisController(autonomous_config)
        # Initially no checkpoint manager (before run)
        assert controller._checkpoint_manager is None


class TestInteractiveModeIntegration:
    """Test interactive mode with checkpoints."""

    def test_interactive_config_has_checkpoints(self, interactive_config):
        """Interactive config should have checkpoints defined."""
        assert len(interactive_config.interactive.checkpoints) > 0
        assert CheckpointType.PROBLEM_CLASSIFICATION in interactive_config.interactive.checkpoints

    def test_checkpoint_manager_initialization(self, interactive_config):
        """CheckpointManager should be created with config checkpoints."""
        manager = CheckpointManager(
            enabled_checkpoints=interactive_config.interactive.checkpoints,
            timeout_seconds=interactive_config.interactive.timeout_seconds,
            auto_confirm_on_timeout=interactive_config.interactive.auto_confirm_on_timeout,
        )

        assert manager.is_enabled(CheckpointType.PROBLEM_CLASSIFICATION)
        assert manager.timeout_seconds == interactive_config.interactive.timeout_seconds

    @pytest.mark.asyncio
    async def test_checkpoint_manager_with_callback(self, interactive_config):
        """CheckpointManager should use callback when provided."""
        callback_called = False

        async def test_callback(data):
            nonlocal callback_called
            callback_called = True
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
            summary="Test checkpoint",
        )

        result = await manager.wait_at(data)

        assert callback_called is True
        assert result.is_confirmed is True

    @pytest.mark.asyncio
    async def test_checkpoint_manager_skips_disabled_checkpoints(self, interactive_config):
        """CheckpointManager should skip disabled checkpoints."""
        manager = CheckpointManager(
            enabled_checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            timeout_seconds=30,
        )

        # FURTHER_DIAGNOSIS is not enabled in this manager
        data = CheckpointData(
            checkpoint_type=CheckpointType.FURTHER_DIAGNOSIS,
            summary="Test checkpoint",
        )

        result = await manager.wait_at(data)

        # Should return confirmed immediately (skipped)
        assert result.is_confirmed is True
        assert result.status == CheckpointStatus.CONFIRMED


class TestCheckpointTimeoutIntegration:
    """Test checkpoint timeout behavior."""

    def test_checkpoint_auto_confirm_setting(self, auto_confirm_config):
        """Auto confirm config should have setting enabled."""
        assert auto_confirm_config.interactive.auto_confirm_on_timeout is True

    def test_checkpoint_no_auto_confirm_setting(self, interactive_config):
        """Interactive config should not have auto confirm."""
        assert interactive_config.interactive.auto_confirm_on_timeout is False

    def test_checkpoint_result_from_timeout_confirmed(self):
        """Checkpoint result can represent timeout with confirm."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.TIMEOUT,
        )

        # TIMEOUT is NOT confirmed by default
        assert result.is_confirmed is False
        assert result.status == CheckpointStatus.TIMEOUT

    def test_checkpoint_confirmed_status(self):
        """Checkpoint result should track confirmed status correctly."""
        confirmed = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CONFIRMED,
        )
        assert confirmed.is_confirmed is True

        modified = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.MODIFIED,
        )
        assert modified.is_confirmed is True  # MODIFIED is also confirmed


class TestModeSwitchingIntegration:
    """Test switching between modes."""

    def test_config_mode_change(self):
        """Configuration should support mode changes."""
        config = DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            ),
            interactive=InteractiveConfig(
                checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            ),
        )

        # Default is interactive
        assert config.default_mode == DiagnosisMode.INTERACTIVE

        # Can determine autonomous for known alert via webhook
        mode = config.determine_mode(
            source="webhook",
            alert_type="VMNetworkLatency",
        )
        assert mode == DiagnosisMode.AUTONOMOUS

        # CLI still defaults to interactive
        mode = config.determine_mode(source="cli", alert_type="VMNetworkLatency")
        assert mode == DiagnosisMode.INTERACTIVE

    def test_controller_accepts_different_configs(self):
        """Controller should accept different mode configs."""
        auto_config = DiagnosisConfig(
            default_mode=DiagnosisMode.AUTONOMOUS,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            ),
        )

        controller = DiagnosisController(auto_config)
        assert controller.config.default_mode == DiagnosisMode.AUTONOMOUS

        int_config = DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            interactive=InteractiveConfig(
                checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            ),
        )

        controller = DiagnosisController(int_config)
        assert controller.config.default_mode == DiagnosisMode.INTERACTIVE


class TestKnownAlertTypesIntegration:
    """Test known alert types configuration."""

    def test_default_known_alert_types(self):
        """Default known alert types should include common types."""
        config = AutonomousConfig(enabled=True, auto_agent_loop=True)

        # Check default known types
        assert "VMNetworkLatency" in config.known_alert_types
        assert "HostNetworkLatency" in config.known_alert_types

    def test_custom_known_alert_types(self):
        """Custom known alert types should be respected."""
        custom_types = ["CustomAlert1", "CustomAlert2"]
        config = AutonomousConfig(
            enabled=True,
            auto_agent_loop=True,
            known_alert_types=custom_types,
        )

        assert config.known_alert_types == custom_types
        assert "VMNetworkLatency" not in config.known_alert_types

    def test_diagnosis_config_is_autonomous_allowed(self):
        """DiagnosisConfig.is_autonomous_allowed should check known types."""
        config = DiagnosisConfig(
            default_mode=DiagnosisMode.AUTONOMOUS,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency", "HostNetworkLatency"],
            ),
        )

        # Known types should be allowed
        assert config.is_autonomous_allowed("VMNetworkLatency") is True
        assert config.is_autonomous_allowed("HostNetworkLatency") is True

        # Unknown type should not be allowed
        assert config.is_autonomous_allowed("UnknownType") is False

        # None should not be allowed
        assert config.is_autonomous_allowed(None) is False
