"""Tests for application settings, including DiagnosisSettings."""

import os

import pytest

from netsherlock.config.settings import (
    DiagnosisSettings,
    Settings,
    get_settings,
    reset_settings,
)
from netsherlock.schemas.config import (
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
)


class TestDiagnosisSettings:
    """Tests for DiagnosisSettings."""

    def test_default_mode_is_interactive(self):
        """Default mode should be interactive."""
        settings = DiagnosisSettings()
        assert settings.default_mode == DiagnosisMode.INTERACTIVE

    def test_autonomous_disabled_by_default(self):
        """Autonomous mode should be disabled by default."""
        settings = DiagnosisSettings()
        assert settings.autonomous_enabled is False
        assert settings.autonomous_auto_agent_loop is False

    def test_interactive_defaults(self):
        """Interactive mode should have sensible defaults."""
        settings = DiagnosisSettings()
        assert len(settings.interactive_checkpoints) == 2
        assert CheckpointType.PROBLEM_CLASSIFICATION in settings.interactive_checkpoints
        assert CheckpointType.MEASUREMENT_PLAN in settings.interactive_checkpoints
        assert settings.interactive_timeout_seconds == 300
        assert settings.interactive_auto_confirm_on_timeout is False

    def test_to_diagnosis_config_creates_valid_config(self):
        """to_diagnosis_config should create valid DiagnosisConfig."""
        settings = DiagnosisSettings()
        config = settings.to_diagnosis_config()

        assert isinstance(config, DiagnosisConfig)
        assert config.default_mode == DiagnosisMode.INTERACTIVE
        assert config.autonomous.enabled is False
        assert config.interactive.timeout_seconds == 300

    def test_custom_settings_to_config(self):
        """Custom settings should be reflected in config."""
        settings = DiagnosisSettings(
            default_mode=DiagnosisMode.AUTONOMOUS,
            autonomous_enabled=True,
            autonomous_auto_agent_loop=True,
            autonomous_known_alert_types=["CustomAlert"],
            interactive_timeout_seconds=60,
        )
        config = settings.to_diagnosis_config()

        assert config.default_mode == DiagnosisMode.AUTONOMOUS
        assert config.autonomous.enabled is True
        assert config.autonomous.auto_agent_loop is True
        assert config.autonomous.known_alert_types == ["CustomAlert"]
        assert config.interactive.timeout_seconds == 60


class TestSettingsIncludesDiagnosis:
    """Tests for Settings including diagnosis configuration."""

    def test_settings_has_diagnosis_field(self):
        """Settings should have diagnosis field."""
        settings = Settings()
        assert hasattr(settings, "diagnosis")
        assert isinstance(settings.diagnosis, DiagnosisSettings)

    def test_get_diagnosis_config_method(self):
        """Settings should have get_diagnosis_config method."""
        settings = Settings()
        config = settings.get_diagnosis_config()

        assert isinstance(config, DiagnosisConfig)
        assert config.default_mode == DiagnosisMode.INTERACTIVE

    def test_diagnosis_settings_defaults_in_settings(self):
        """Diagnosis settings in Settings should have correct defaults."""
        settings = Settings()
        assert settings.diagnosis.default_mode == DiagnosisMode.INTERACTIVE
        assert settings.diagnosis.autonomous_enabled is False


class TestSettingsSingleton:
    """Tests for settings singleton behavior."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Reset settings after each test."""
        reset_settings()

    def test_get_settings_returns_same_instance(self):
        """get_settings should return same instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_reset_settings_clears_singleton(self):
        """reset_settings should clear singleton."""
        s1 = get_settings()
        reset_settings()
        s2 = get_settings()
        assert s1 is not s2


class TestDiagnosisSettingsFromEnv:
    """Tests for loading diagnosis settings from environment."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up environment and reset settings."""
        # Clean up any DIAGNOSIS_ env vars
        for key in list(os.environ.keys()):
            if key.startswith("DIAGNOSIS_"):
                del os.environ[key]
        reset_settings()

    def test_mode_from_env(self):
        """Should load default_mode from environment."""
        os.environ["DIAGNOSIS_DEFAULT_MODE"] = "autonomous"
        settings = DiagnosisSettings()
        assert settings.default_mode == DiagnosisMode.AUTONOMOUS

    def test_autonomous_enabled_from_env(self):
        """Should load autonomous_enabled from environment."""
        os.environ["DIAGNOSIS_AUTONOMOUS_ENABLED"] = "true"
        settings = DiagnosisSettings()
        assert settings.autonomous_enabled is True

    def test_timeout_from_env(self):
        """Should load interactive_timeout_seconds from environment."""
        os.environ["DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS"] = "120"
        settings = DiagnosisSettings()
        assert settings.interactive_timeout_seconds == 120
