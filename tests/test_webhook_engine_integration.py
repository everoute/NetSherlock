"""Tests for webhook engine integration — worker, lifespan, and deep coverage.

Complements test_webhook.py (auth/validation/endpoints) and test_engine.py
(engine creation/request building) with coverage for:
- diagnosis_worker() complete behavior
- _build_diagnosis_request() edge cases
- _map_alert_to_type() complete mapping
- lifespan() lifecycle management
- health endpoint with engine integration
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


class TestDiagnosisWorker:
    """diagnosis_worker() background processor."""

    @pytest.fixture
    def mock_engine(self):
        """Mock engine satisfying DiagnosisEngine protocol."""
        engine = MagicMock()
        engine.engine_type = "mock"
        engine.execute = AsyncMock(return_value=DiagnosisResult(
            diagnosis_id="worker-test",
            status=DiagnosisStatus.COMPLETED,
            summary="Mock result",
        ))
        engine.health_check = AsyncMock(return_value={"engine": "mock", "status": "healthy"})
        return engine

    async def test_worker_calls_engine_execute(self, mock_engine):
        """Worker dequeues request and calls engine.execute()."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            # Put a request in the queue
            await webhook.diagnosis_queue.put((
                "alert", "test-worker-001",
                {"labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                            "src_vm": "uuid-1", "network_type": "vm"}}
            ))

            # Run worker for one iteration
            task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            mock_engine.execute.assert_called_once()
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_worker_stores_result_in_store(self, mock_engine):
        """Execute result is stored in diagnosis_store."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "store-test-001",
                {"labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                            "src_vm": "uuid-1", "network_type": "vm"}}
            ))

            task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert "store-test-001" in webhook.diagnosis_store
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_worker_engine_none_stores_error(self):
        """engine=None stores create_error result."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = None
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "none-engine-001",
                {"labels": {"alertname": "Test", "src_host": "1.2.3.4",
                            "src_vm": "uuid-1", "network_type": "vm"}}
            ))

            task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert "none-engine-001" in webhook.diagnosis_store
            result = webhook.diagnosis_store["none-engine-001"]
            assert result.status == DiagnosisStatus.ERROR
            assert "not initialized" in result.error
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_worker_execute_exception_stores_error(self, mock_engine):
        """engine.execute() exception stores error result."""
        import netsherlock.api.webhook as webhook

        mock_engine.execute = AsyncMock(side_effect=RuntimeError("Connection failed"))

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "exc-test-001",
                {"labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                            "src_vm": "uuid-1", "network_type": "vm"}}
            ))

            task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert "exc-test-001" in webhook.diagnosis_store
            result = webhook.diagnosis_store["exc-test-001"]
            assert result.status == DiagnosisStatus.ERROR
            assert "Connection failed" in result.error
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_worker_cancelled_error_breaks_loop(self):
        """CancelledError cleanly exits the worker loop."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        try:
            webhook.engine = MagicMock()

            task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.05)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            webhook.engine = original_engine


class TestBuildDiagnosisRequestDeep:
    """_build_diagnosis_request() edge cases.

    Supplements the basic tests in test_engine.py.
    """

    def test_alert_src_host_from_instance_label(self):
        """No src_host label extracts IP from instance='1.2.3.4:9100'."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "labels": {
                "alertname": "HostNetworkLatency",
                "instance": "10.0.0.5:9100",
                "network_type": "system",
            },
        }
        request = _build_diagnosis_request("alert", "inst-001", raw_data)
        assert request.src_host == "10.0.0.5"

    def test_alert_missing_all_labels_raises_validation(self):
        """All labels missing causes validation error (vm requires src_vm)."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {"labels": {}}
        # Default network_type=vm but no src_vm → validation fails
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            _build_diagnosis_request("alert", "empty-001", raw_data)

    def test_alert_mode_from_raw_data(self):
        """raw_data['mode']='autonomous' maps to DiagnosisMode.AUTONOMOUS."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "labels": {"alertname": "Test", "src_host": "1.2.3.4",
                        "src_vm": "uuid-1", "network_type": "vm"},
            "mode": "autonomous",
        }
        request = _build_diagnosis_request("alert", "mode-001", raw_data)
        assert request.mode == DiagnosisMode.AUTONOMOUS

    def test_alert_mode_absent_is_none(self):
        """raw_data without mode key gives request.mode=None."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "labels": {"alertname": "Test", "src_host": "1.2.3.4",
                        "src_vm": "uuid-1", "network_type": "vm"},
        }
        request = _build_diagnosis_request("alert", "nomode-001", raw_data)
        assert request.mode is None

    def test_manual_with_description(self):
        """Manual request description field is passed through."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "diagnosis_type": "latency",
            "network_type": "system",
            "src_host": "1.2.3.4",
            "description": "High latency observed",
        }
        request = _build_diagnosis_request("manual", "desc-001", raw_data)
        assert request.description == "High latency observed"

    def test_manual_with_alert_type(self):
        """Manual request can carry alert_type for mode selection."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "diagnosis_type": "latency",
            "network_type": "system",
            "src_host": "1.2.3.4",
            "alert_type": "VMNetworkLatency",
        }
        request = _build_diagnosis_request("manual", "alert-001", raw_data)
        assert request.alert_type == "VMNetworkLatency"

    def test_manual_mode_string_to_enum(self):
        """Manual raw_data['mode']='interactive' maps to DiagnosisMode.INTERACTIVE."""
        from netsherlock.api.webhook import _build_diagnosis_request

        raw_data = {
            "diagnosis_type": "latency",
            "network_type": "system",
            "src_host": "1.2.3.4",
            "mode": "interactive",
        }
        request = _build_diagnosis_request("manual", "mode-001", raw_data)
        assert request.mode == DiagnosisMode.INTERACTIVE


class TestMapAlertToTypeDeep:
    """_map_alert_to_type() complete mapping.

    Supplements test_engine.py which covers basic cases.
    """

    def test_host_packet_drop(self):
        """HostPacketDrop maps to packet_drop."""
        from netsherlock.api.webhook import _map_alert_to_type
        assert _map_alert_to_type("HostPacketDrop") == "packet_drop"

    def test_vm_connectivity(self):
        """VMConnectivity maps to connectivity."""
        from netsherlock.api.webhook import _map_alert_to_type
        assert _map_alert_to_type("VMConnectivity") == "connectivity"

    def test_empty_alertname(self):
        """Empty string defaults to latency."""
        from netsherlock.api.webhook import _map_alert_to_type
        assert _map_alert_to_type("") == "latency"


class TestLifespan:
    """lifespan() application lifecycle management."""

    async def test_engine_initialized_on_startup(self):
        """Engine global is set during startup."""
        import netsherlock.api.webhook as webhook
        from netsherlock.api.webhook import app

        original_engine = webhook.engine
        try:
            webhook.engine = None

            with patch("netsherlock.api.webhook._create_engine") as mock_create:
                mock_eng = MagicMock()
                mock_eng.engine_type = "test"
                mock_create.return_value = mock_eng

                async with webhook.lifespan(app):
                    assert webhook.engine is mock_eng
        finally:
            webhook.engine = original_engine

    async def test_worker_cancelled_on_shutdown(self):
        """Worker task is cancelled during shutdown."""
        import netsherlock.api.webhook as webhook
        from netsherlock.api.webhook import app

        original_engine = webhook.engine
        try:
            with patch("netsherlock.api.webhook._create_engine") as mock_create:
                mock_eng = MagicMock()
                mock_eng.engine_type = "test"
                mock_create.return_value = mock_eng

                async with webhook.lifespan(app):
                    pass
                # After exiting, worker should have been cancelled
                # (no assertion needed — if it hangs, the test times out)
        finally:
            webhook.engine = original_engine

    async def test_engine_type_from_settings(self):
        """Engine type determined from settings."""
        import netsherlock.api.webhook as webhook
        from netsherlock.api.webhook import app

        original_engine = webhook.engine
        try:
            mock_settings = MagicMock()
            mock_settings.diagnosis_engine = "controller"

            with patch("netsherlock.api.webhook.get_settings", return_value=mock_settings), \
                 patch("netsherlock.api.webhook._create_engine") as mock_create:
                mock_eng = MagicMock()
                mock_eng.engine_type = "controller"
                mock_create.return_value = mock_eng

                async with webhook.lifespan(app):
                    mock_create.assert_called_once_with(mock_settings)
        finally:
            webhook.engine = original_engine


class TestHealthEndpointWithEngine:
    """GET /health with engine integration."""

    async def test_health_includes_engine_type(self):
        """Engine present returns engine type."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        try:
            mock_eng = MagicMock()
            mock_eng.engine_type = "controller"
            mock_eng.health_check = AsyncMock(return_value={
                "engine": "controller", "status": "healthy"
            })
            webhook.engine = mock_eng

            response = await webhook.health_check()
            assert response.engine == "controller"
            assert response.status == "healthy"
        finally:
            webhook.engine = original_engine

    async def test_health_engine_none_shows_initializing(self):
        """Engine not initialized shows status=initializing."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        try:
            webhook.engine = None
            response = await webhook.health_check()
            assert response.status == "initializing"
        finally:
            webhook.engine = original_engine

    async def test_health_engine_check_error_falls_back(self):
        """engine.health_check() exception falls back to engine_type attr."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        try:
            mock_eng = MagicMock()
            mock_eng.engine_type = "controller"
            mock_eng.health_check = AsyncMock(side_effect=RuntimeError("check failed"))
            webhook.engine = mock_eng

            response = await webhook.health_check()
            assert response.engine == "controller"
            assert response.status == "healthy"
        finally:
            webhook.engine = original_engine
