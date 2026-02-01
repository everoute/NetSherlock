"""Tests for DiagnosisEngine protocol and ControllerEngine.

Tests the engine abstraction layer introduced in Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netsherlock.core.engine import DiagnosisEngine
from netsherlock.core.controller_engine import ControllerEngine
from netsherlock.schemas.config import (
    AutonomousConfig,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


class TestDiagnosisEngineProtocol:
    """Tests for the DiagnosisEngine Protocol."""

    def test_controller_engine_satisfies_protocol(self):
        """ControllerEngine should satisfy DiagnosisEngine protocol."""
        config = DiagnosisConfig()
        engine = ControllerEngine(config=config)

        # Check protocol attributes exist
        assert hasattr(engine, "engine_type")
        assert hasattr(engine, "execute")
        assert hasattr(engine, "health_check")

    def test_engine_type_is_controller(self):
        """ControllerEngine.engine_type should be 'controller'."""
        config = DiagnosisConfig()
        engine = ControllerEngine(config=config)
        assert engine.engine_type == "controller"


class TestControllerEngine:
    """Tests for ControllerEngine."""

    @pytest.fixture
    def config(self):
        """Default test config."""
        return DiagnosisConfig(
            default_mode=DiagnosisMode.INTERACTIVE,
            autonomous=AutonomousConfig(
                enabled=True,
                auto_agent_loop=True,
            ),
        )

    @pytest.fixture
    def engine(self, config):
        """Create ControllerEngine with test config."""
        return ControllerEngine(
            config=config,
            llm_model="claude-haiku-4-5-20251001",
        )

    @pytest.fixture
    def system_request(self):
        """System network diagnosis request."""
        return DiagnosisRequest(
            request_id="test-engine-001",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
            source=DiagnosisRequestSource.CLI,
            mode=DiagnosisMode.AUTONOMOUS,
        )

    @pytest.fixture
    def webhook_request(self):
        """Webhook diagnosis request."""
        return DiagnosisRequest(
            request_id="test-engine-002",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
            source=DiagnosisRequestSource.WEBHOOK,
            alert_type="VMNetworkLatency",
        )

    @pytest.mark.asyncio
    async def test_execute_creates_controller(self, engine, system_request):
        """execute() should create a DiagnosisController and call run()."""
        mock_result = DiagnosisResult(
            diagnosis_id="test-engine-001",
            status=DiagnosisStatus.COMPLETED,
            mode=DiagnosisMode.AUTONOMOUS,
        )

        with patch(
            "netsherlock.core.controller_engine.DiagnosisController"
        ) as MockController:
            mock_instance = MockController.return_value
            mock_instance.run = AsyncMock(return_value=mock_result)

            result = await engine.execute(request=system_request)

            # Controller should have been created
            MockController.assert_called_once()

            # run() should have been called with the request
            mock_instance.run.assert_called_once()
            call_kwargs = mock_instance.run.call_args
            assert call_kwargs.kwargs["request"] == system_request
            assert call_kwargs.kwargs["source"] == DiagnosisRequestSource.CLI

            # Should return the controller's result
            assert result.diagnosis_id == "test-engine-001"
            assert result.status == DiagnosisStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_webhook_no_checkpoint_callback(self, config):
        """Webhook requests should not get a checkpoint callback."""
        engine = ControllerEngine(
            config=config,
            checkpoint_callback=lambda data: None,  # Provide callback
        )

        request = DiagnosisRequest(
            request_id="webhook-test",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
            source=DiagnosisRequestSource.WEBHOOK,
        )

        mock_result = DiagnosisResult(
            diagnosis_id="webhook-test",
            status=DiagnosisStatus.COMPLETED,
        )

        with patch(
            "netsherlock.core.controller_engine.DiagnosisController"
        ) as MockController:
            mock_instance = MockController.return_value
            mock_instance.run = AsyncMock(return_value=mock_result)

            await engine.execute(request=request)

            # Controller should have been created without checkpoint callback
            init_kwargs = MockController.call_args.kwargs
            assert init_kwargs.get("checkpoint_callback") is None

    @pytest.mark.asyncio
    async def test_health_check(self, engine):
        """health_check() should return engine info."""
        health = await engine.health_check()

        assert health["engine"] == "controller"
        assert health["status"] == "healthy"
        assert "config" in health
        assert health["config"]["model"] == "claude-haiku-4-5-20251001"

    def test_engine_init_stores_paths(self):
        """Engine should store all path configurations."""
        config = DiagnosisConfig()
        engine = ControllerEngine(
            config=config,
            global_inventory_path="/path/to/inventory.yaml",
            minimal_input_path="/path/to/input.yaml",
            project_path="/path/to/project",
            bpf_local_tools_path="/path/to/local",
            bpf_remote_tools_path="/path/to/remote",
        )

        assert engine._global_inventory_path == "/path/to/inventory.yaml"
        assert engine._minimal_input_path == "/path/to/input.yaml"
        assert engine._project_path == "/path/to/project"


class TestWebhookEngineCreation:
    """Tests for _create_engine in webhook."""

    def test_create_controller_engine(self):
        """_create_engine with 'controller' should create ControllerEngine."""
        from netsherlock.api.webhook import _create_engine

        mock_settings = MagicMock()
        mock_settings.diagnosis_engine = "controller"
        mock_settings.get_diagnosis_config.return_value = DiagnosisConfig()
        mock_settings.global_inventory_path = None
        mock_settings.project_path = None
        mock_settings.llm.model = "claude-haiku-4-5-20251001"
        mock_settings.llm.max_turns = None
        mock_settings.llm.max_budget_usd = None
        mock_settings.bpf_tools.local_tools_path = "/tmp/tools"
        mock_settings.bpf_tools.remote_tools_path = "/tmp/remote"

        engine = _create_engine(mock_settings)

        assert isinstance(engine, ControllerEngine)
        assert engine.engine_type == "controller"

    def test_create_unknown_engine_raises(self):
        """_create_engine with unknown type should raise ValueError."""
        from netsherlock.api.webhook import _create_engine

        mock_settings = MagicMock()
        mock_settings.diagnosis_engine = "invalid"

        with pytest.raises(ValueError, match="Unknown engine type"):
            _create_engine(mock_settings)


class TestBuildDiagnosisRequest:
    """Tests for _build_diagnosis_request in webhook."""

    def test_build_alert_request(self):
        """Alert data should be converted to DiagnosisRequest."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "labels": {
                "alertname": "VMNetworkLatency",
                "network_type": "vm",
                "src_host": "192.168.1.10",
                "src_vm": "uuid-1234",
                "dst_host": "192.168.1.20",
                "dst_vm": "uuid-5678",
            },
            "mode": "autonomous",
        }

        request = _build_diagnosis_request("alert", "test-id", raw_data)

        assert request.request_id == "test-id"
        assert request.request_type == "latency"
        assert request.network_type == "vm"
        assert request.src_host == "192.168.1.10"
        assert request.src_vm == "uuid-1234"
        assert request.source == DiagnosisRequestSource.WEBHOOK
        assert request.alert_type == "VMNetworkLatency"
        assert request.mode == DiagnosisMode.AUTONOMOUS

    def test_build_manual_request(self):
        """Manual data should be converted to DiagnosisRequest."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "diagnosis_type": "packet_drop",
            "network_type": "system",
            "src_host": "192.168.1.10",
            "mode": "interactive",
        }

        request = _build_diagnosis_request("manual", "manual-id", raw_data)

        assert request.request_id == "manual-id"
        assert request.request_type == "packet_drop"
        assert request.network_type == "system"
        assert request.source == DiagnosisRequestSource.API
        assert request.mode == DiagnosisMode.INTERACTIVE

    def test_build_alert_request_extracts_host_from_instance(self):
        """Alert request should extract host from instance label."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "labels": {
                "alertname": "HostNetworkLatency",
                "network_type": "system",
                "instance": "192.168.1.10:9090",
            },
        }

        request = _build_diagnosis_request("alert", "test-id", raw_data)
        assert request.src_host == "192.168.1.10"


class TestMapAlertToType:
    """Tests for _map_alert_to_type."""

    def test_known_alert_types(self):
        """Known alert types should map correctly."""
        from netsherlock.api.webhook import _map_alert_to_type

        assert _map_alert_to_type("VMNetworkLatency") == "latency"
        assert _map_alert_to_type("HostNetworkLatency") == "latency"
        assert _map_alert_to_type("VMPacketDrop") == "packet_drop"
        assert _map_alert_to_type("HostPacketDrop") == "packet_drop"
        assert _map_alert_to_type("VMConnectivity") == "connectivity"

    def test_unknown_alert_defaults_to_latency(self):
        """Unknown alert types should default to latency."""
        from netsherlock.api.webhook import _map_alert_to_type

        assert _map_alert_to_type("UnknownAlert") == "latency"
        assert _map_alert_to_type("") == "latency"


class TestSettingsEngineFields:
    """Tests for new engine-related settings fields."""

    def test_default_engine_is_controller(self):
        """Default diagnosis_engine should be 'controller'."""
        from netsherlock.config.settings import Settings

        settings = Settings()
        assert settings.diagnosis_engine == "controller"

    def test_default_paths_are_none(self):
        """Default global_inventory_path and project_path should be None."""
        from netsherlock.config.settings import Settings

        settings = Settings()
        assert settings.global_inventory_path is None
        assert settings.project_path is None
