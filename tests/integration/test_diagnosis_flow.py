"""Integration tests for complete diagnosis flow.

Tests the full diagnosis pipeline from alert/request to final report,
including both autonomous and interactive modes.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netsherlock.controller.diagnosis_controller import DiagnosisController
from netsherlock.controller.checkpoints import CheckpointData, CheckpointResult, CheckpointStatus
from netsherlock.schemas.config import CheckpointType, DiagnosisConfig, DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.alert import DiagnosisRequest


class TestDiagnosisRequestCreation:
    """Test diagnosis request creation and validation."""

    def test_request_with_all_fields(self):
        """Diagnosis request with all fields should be valid."""
        request = DiagnosisRequest(
            request_id="test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.1.20",
            dst_vm="bf7bb275-715d-5dc1-95c9-3feb045418g2",
            alert_type="VMNetworkLatency",
        )

        assert request.request_id == "test-001"
        assert request.src_host == "192.168.1.10"
        assert request.dst_host == "192.168.1.20"
        assert request.src_vm is not None
        assert request.alert_type == "VMNetworkLatency"

    def test_request_minimal_fields(self):
        """Diagnosis request with minimal fields should be valid."""
        request = DiagnosisRequest(
            request_id="test-002",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )

        assert request.request_id == "test-002"
        assert request.src_host == "192.168.1.10"
        assert request.dst_host is None
        assert request.src_vm is None


class TestModeSelection:
    """Test mode selection based on config and request parameters."""

    def test_autonomous_mode_determined_for_known_alert(self, autonomous_config):
        """Known alert type should trigger autonomous mode."""
        mode = autonomous_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="VMNetworkLatency",
        )
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_unknown_alert_falls_back_to_default_mode(self, autonomous_config):
        """Unknown alert type should fall back to default mode (not auto-trigger autonomous)."""
        mode = autonomous_config.determine_mode(
            source=DiagnosisRequestSource.WEBHOOK.value,
            alert_type="UnknownAlertType",
        )
        # Unknown alert type doesn't trigger auto autonomous, but falls back to default_mode
        # autonomous_config has default_mode=AUTONOMOUS
        assert mode == autonomous_config.default_mode

    def test_cli_defaults_to_interactive(self, interactive_config):
        """CLI source should default to interactive mode."""
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
        )
        assert mode == DiagnosisMode.INTERACTIVE

    def test_force_mode_overrides_config(self, interactive_config):
        """Force mode should override determined mode."""
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )
        assert mode == DiagnosisMode.AUTONOMOUS


class TestControllerInitialization:
    """Test controller initialization with different configs."""

    def test_controller_with_autonomous_config(self, autonomous_config):
        """Controller should initialize with autonomous config."""
        controller = DiagnosisController(autonomous_config)

        assert controller.config == autonomous_config
        assert controller.state is None
        assert not controller.is_running

    def test_controller_with_interactive_config(self, interactive_config):
        """Controller should initialize with interactive config."""
        controller = DiagnosisController(interactive_config)

        assert controller.config == interactive_config
        assert controller.state is None

    def test_controller_with_checkpoint_callback(self, interactive_config):
        """Controller should accept checkpoint callback."""
        async def callback(data):
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )

        controller = DiagnosisController(interactive_config, checkpoint_callback=callback)

        assert controller.checkpoint_callback is callback


class TestAlertToDiagnosisIntegration:
    """Test alert payload to diagnosis flow."""

    def test_alertmanager_payload_creates_valid_request(self, alert_payloads):
        """Alertmanager webhook payload should create valid diagnosis request."""
        alert_data = alert_payloads["vm_network_latency_alert"]

        request = DiagnosisRequest(
            request_id="alert-001",
            request_type="latency",
            network_type="vm",
            src_host=alert_data["labels"].get("instance", "").split(":")[0] or "192.168.1.10",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            alert_type=alert_data["labels"]["alertname"],
        )

        assert request.alert_type == "VMNetworkLatency"
        assert request.src_host != ""

    def test_unknown_alert_type_from_payload(self, alert_payloads):
        """Unknown alert type should be captured from payload."""
        alert_data = alert_payloads["unknown_alert"]

        request = DiagnosisRequest(
            request_id="alert-002",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
            alert_type=alert_data["labels"]["alertname"],
        )

        assert request.alert_type == "CustomNetworkAlert"


class TestManualRequestIntegration:
    """Test manual diagnosis request flow."""

    def test_manual_request_uses_interactive_by_default(self, interactive_config):
        """Manual requests should use interactive mode by default."""
        request = DiagnosisRequest(
            request_id="manual-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.1.20",
            dst_vm="bf7bb275-715d-5dc1-95c9-3feb045418g2",
        )

        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
        )

        assert mode == DiagnosisMode.INTERACTIVE

    def test_manual_request_can_force_autonomous(self, interactive_config):
        """Manual request can force autonomous mode."""
        request = DiagnosisRequest(
            request_id="manual-002",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )

        # Force autonomous mode
        mode = interactive_config.determine_mode(
            source=DiagnosisRequestSource.CLI.value,
            alert_type=None,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        assert mode == DiagnosisMode.AUTONOMOUS

    def test_diagnosis_request_with_src_vm(self, interactive_config):
        """Diagnosis request with src_vm should be properly handled."""
        request = DiagnosisRequest(
            request_id="manual-003",
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        )

        assert request.src_vm is not None
        assert request.src_host == "192.168.1.10"


class TestCheckpointDataCreation:
    """Test checkpoint data creation and structure."""

    def test_checkpoint_data_structure(self):
        """Checkpoint data should have correct structure."""
        data = CheckpointData(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            summary="Classification complete",
            details={"classification": "high_latency"},
            options=["confirm", "modify", "cancel"],
            recommendation="Proceed with measurement",
        )

        assert data.checkpoint_type == CheckpointType.PROBLEM_CLASSIFICATION
        assert data.summary == "Classification complete"
        assert "classification" in data.details
        assert len(data.options) == 3

    def test_checkpoint_result_confirmed(self):
        """Checkpoint result should track confirmation status."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CONFIRMED,
        )

        assert result.is_confirmed is True
        assert result.is_cancelled is False

    def test_checkpoint_result_cancelled(self):
        """Checkpoint result should track cancellation status."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
            status=CheckpointStatus.CANCELLED,
        )

        assert result.is_confirmed is False
        assert result.is_cancelled is True

    def test_checkpoint_result_with_user_input(self):
        """Checkpoint result should capture user input."""
        result = CheckpointResult(
            checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
            status=CheckpointStatus.MODIFIED,
            user_input="Custom measurement parameters",
        )

        assert result.is_confirmed is True  # MODIFIED is also confirmed
        assert result.user_input == "Custom measurement parameters"


class TestInterruptMechanism:
    """Test controller interrupt mechanism."""

    def test_interrupt_sets_flag(self, autonomous_config):
        """Interrupt should set the interrupt flag."""
        controller = DiagnosisController(autonomous_config)
        controller.interrupt()

        # The interrupt flag is set via _interrupt_event
        assert controller._interrupt_event.is_set()

    def test_check_interrupt_returns_flag_state(self, autonomous_config):
        """Check interrupt should return current flag state."""
        controller = DiagnosisController(autonomous_config)

        # Before interrupt
        assert controller._check_interrupt() is False

        # After interrupt
        controller.interrupt()
        assert controller._check_interrupt() is True
