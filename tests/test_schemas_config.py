"""Tests for diagnosis configuration schemas."""

import pytest
from pydantic import ValidationError

from netsherlock.schemas.config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    InteractiveConfig,
)


class TestDiagnosisMode:
    """Tests for DiagnosisMode enum."""

    def test_mode_values(self):
        """Mode enum has expected values."""
        assert DiagnosisMode.AUTONOMOUS.value == "autonomous"
        assert DiagnosisMode.INTERACTIVE.value == "interactive"

    def test_mode_from_string(self):
        """Mode can be created from string."""
        assert DiagnosisMode("autonomous") == DiagnosisMode.AUTONOMOUS
        assert DiagnosisMode("interactive") == DiagnosisMode.INTERACTIVE


class TestCheckpointType:
    """Tests for CheckpointType enum."""

    def test_checkpoint_values(self):
        """Checkpoint enum has expected values."""
        assert CheckpointType.PROBLEM_CLASSIFICATION.value == "problem_classification"
        assert CheckpointType.MEASUREMENT_PLAN.value == "measurement_plan"
        assert CheckpointType.FURTHER_DIAGNOSIS.value == "further_diagnosis"


class TestAutonomousConfig:
    """Tests for AutonomousConfig."""

    def test_defaults(self):
        """Default values are correct."""
        config = AutonomousConfig()
        assert config.enabled is True
        assert config.auto_agent_loop is False
        assert config.interrupt_enabled is True
        assert "VMNetworkLatency" in config.known_alert_types

    def test_custom_alert_types(self):
        """Can specify custom alert types."""
        config = AutonomousConfig(known_alert_types=["CustomAlert"])
        assert config.known_alert_types == ["CustomAlert"]


class TestInteractiveConfig:
    """Tests for InteractiveConfig."""

    def test_defaults(self):
        """Default values are correct."""
        config = InteractiveConfig()
        assert CheckpointType.PROBLEM_CLASSIFICATION in config.checkpoints
        assert CheckpointType.MEASUREMENT_PLAN in config.checkpoints
        assert config.timeout_seconds == 300
        assert config.auto_confirm_on_timeout is False

    def test_timeout_validation_min(self):
        """Timeout must be at least 30 seconds."""
        with pytest.raises(ValidationError):
            InteractiveConfig(timeout_seconds=10)

    def test_timeout_validation_max(self):
        """Timeout must be at most 3600 seconds."""
        with pytest.raises(ValidationError):
            InteractiveConfig(timeout_seconds=7200)

    def test_valid_timeout(self):
        """Valid timeout values are accepted."""
        config = InteractiveConfig(timeout_seconds=600)
        assert config.timeout_seconds == 600


class TestDiagnosisConfig:
    """Tests for DiagnosisConfig."""

    def test_default_mode_is_interactive(self):
        """Default mode should be interactive."""
        config = DiagnosisConfig()
        assert config.default_mode == DiagnosisMode.INTERACTIVE

    def test_nested_config_defaults(self):
        """Nested configs have correct defaults."""
        config = DiagnosisConfig()
        assert isinstance(config.autonomous, AutonomousConfig)
        assert isinstance(config.interactive, InteractiveConfig)

    def test_custom_default_mode(self):
        """Can set custom default mode."""
        config = DiagnosisConfig(default_mode=DiagnosisMode.AUTONOMOUS)
        assert config.default_mode == DiagnosisMode.AUTONOMOUS

    def test_from_dict(self):
        """Can create from dictionary."""
        data = {
            "default_mode": "autonomous",
            "autonomous": {"auto_agent_loop": True},
            "interactive": {"timeout_seconds": 600},
        }
        config = DiagnosisConfig.model_validate(data)
        assert config.default_mode == DiagnosisMode.AUTONOMOUS
        assert config.autonomous.auto_agent_loop is True
        assert config.interactive.timeout_seconds == 600


class TestDiagnosisConfigMethods:
    """Tests for DiagnosisConfig methods."""

    def test_is_autonomous_allowed_disabled(self):
        """Autonomous not allowed when disabled."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(enabled=False)
        )
        assert config.is_autonomous_allowed() is False

    def test_is_autonomous_allowed_no_auto_loop(self):
        """Autonomous not allowed without auto_agent_loop."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(enabled=True, auto_agent_loop=False)
        )
        assert config.is_autonomous_allowed() is False

    def test_is_autonomous_allowed_unknown_alert(self):
        """Autonomous not allowed for unknown alert types."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )
        assert config.is_autonomous_allowed("UnknownAlert") is False

    def test_is_autonomous_allowed_known_alert(self):
        """Autonomous allowed for known alert types."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )
        assert config.is_autonomous_allowed("VMNetworkLatency") is True

    def test_determine_mode_force_override(self):
        """Force mode overrides all logic."""
        config = DiagnosisConfig(default_mode=DiagnosisMode.INTERACTIVE)
        result = config.determine_mode(
            source="cli",
            force_mode=DiagnosisMode.AUTONOMOUS,
        )
        assert result == DiagnosisMode.AUTONOMOUS

    def test_determine_mode_cli_default_interactive(self):
        """CLI defaults to interactive."""
        config = DiagnosisConfig(default_mode=DiagnosisMode.AUTONOMOUS)
        result = config.determine_mode(source="cli")
        assert result == DiagnosisMode.INTERACTIVE

    def test_determine_mode_webhook_autonomous(self):
        """Webhook with auto_loop and known alert triggers autonomous."""
        config = DiagnosisConfig(
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )
        result = config.determine_mode(
            source="webhook",
            alert_type="VMNetworkLatency",
        )
        assert result == DiagnosisMode.AUTONOMOUS

    def test_determine_mode_webhook_unknown_alert(self):
        """Webhook with unknown alert uses default."""
        config = DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
                known_alert_types=["VMNetworkLatency"],
            )
        )
        result = config.determine_mode(
            source="webhook",
            alert_type="UnknownAlert",
        )
        assert result == DiagnosisMode.INTERACTIVE

    def test_determine_mode_api_uses_default(self):
        """API uses default mode."""
        config = DiagnosisConfig(default_mode=DiagnosisMode.AUTONOMOUS)
        result = config.determine_mode(source="api")
        assert result == DiagnosisMode.AUTONOMOUS


class TestDiagnosisConfigSerialization:
    """Tests for config serialization."""

    def test_to_json(self):
        """Config can be serialized to JSON."""
        config = DiagnosisConfig()
        json_str = config.model_dump_json()
        assert "interactive" in json_str
        assert "autonomous" in json_str

    def test_roundtrip(self):
        """Config survives serialization roundtrip."""
        original = DiagnosisConfig(
            default_mode=DiagnosisMode.AUTONOMOUS,
            autonomous=AutonomousConfig(auto_agent_loop=True),
        )
        json_str = original.model_dump_json()
        restored = DiagnosisConfig.model_validate_json(json_str)
        assert restored.default_mode == original.default_mode
        assert restored.autonomous.auto_agent_loop == original.autonomous.auto_agent_loop
