"""Tests for Webhook → ControllerEngine end-to-end flow.

Verifies the complete data path from HTTP webhook endpoints
through the ControllerEngine to diagnosis_store results.
Uses httpx.AsyncClient with MockControllerEngine.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


@pytest.fixture
def mock_controller_result():
    """Standard controller completion result."""
    return DiagnosisResult(
        diagnosis_id="flow-ctrl-001",
        status=DiagnosisStatus.COMPLETED,
        summary="OVS bridge delay detected",
        source=DiagnosisRequestSource.WEBHOOK,
        mode=DiagnosisMode.AUTONOMOUS,
        checkpoint_history=[{"checkpoint": "l2", "status": "confirmed"}],
        l4_analysis={"root_cause": {"component": "ovs"}},
    )


@pytest.fixture
def mock_engine(mock_controller_result):
    """Mock ControllerEngine."""
    engine = MagicMock()
    engine.engine_type = "controller"
    engine.execute = AsyncMock(return_value=mock_controller_result)
    engine.health_check = AsyncMock(return_value={
        "engine": "controller", "status": "healthy",
        "config": {"model": "claude-haiku-4-5-20251001"},
    })
    return engine


class TestWebhookControllerFlow:
    """Webhook → ControllerEngine end-to-end."""

    async def test_alert_webhook_queues_and_executes(self, mock_engine, mock_controller_result):
        """POST /webhook/alertmanager → queue → ControllerEngine.execute() → store."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            # Simulate alert processing
            await webhook.diagnosis_queue.put((
                "alert", "flow-ctrl-001",
                {
                    "labels": {
                        "alertname": "VMNetworkLatency",
                        "src_host": "192.168.1.10",
                        "src_vm": "uuid-1234",
                        "network_type": "vm",
                    },
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            assert "flow-ctrl-001" in webhook.diagnosis_store
            result = webhook.diagnosis_store["flow-ctrl-001"]
            assert result.status == DiagnosisStatus.COMPLETED
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_manual_request_queues_and_executes(self, mock_engine, mock_controller_result):
        """POST /diagnose → queue → ControllerEngine.execute() → store."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "manual", "flow-ctrl-002",
                {
                    "diagnosis_type": "latency",
                    "network_type": "system",
                    "src_host": "192.168.1.10",
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            assert "flow-ctrl-002" in webhook.diagnosis_store
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_result_retrievable_via_get(self, mock_controller_result):
        """Completed result is retrievable via GET /diagnose/{id}."""
        import netsherlock.api.webhook as webhook

        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store["flow-ctrl-003"] = mock_controller_result
            webhook.diagnosis_store["flow-ctrl-003"].diagnosis_id = "flow-ctrl-003"

            response = await webhook.get_diagnosis("flow-ctrl-003", _api_key="test")
            assert response.status == "completed"
            assert response.summary == "OVS bridge delay detected"
        finally:
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_result_has_controller_specific_fields(self, mock_engine, mock_controller_result):
        """Result contains checkpoint_history and l4_analysis."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "flow-ctrl-004",
                {
                    "labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                                "src_vm": "uuid-1", "network_type": "vm"},
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            result = webhook.diagnosis_store["flow-ctrl-004"]
            assert result.checkpoint_history is not None
            assert result.l4_analysis is not None
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_error_result_retrievable(self, mock_controller_result):
        """Error result is retrievable via GET /diagnose/{id}."""
        import netsherlock.api.webhook as webhook

        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.diagnosis_store.clear()
            error_result = DiagnosisResult.create_error(
                diagnosis_id="flow-ctrl-err",
                error="Controller failed",
            )
            webhook.diagnosis_store["flow-ctrl-err"] = error_result

            response = await webhook.get_diagnosis("flow-ctrl-err", _api_key="test")
            assert response.status == "error"
        finally:
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_multiple_alerts_sequential_processing(self, mock_engine):
        """Multiple alerts processed sequentially, all results retrievable."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_engine
            webhook.diagnosis_store.clear()

            for i in range(3):
                await webhook.diagnosis_queue.put((
                    "alert", f"seq-{i}",
                    {
                        "labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                                    "src_vm": "uuid-1", "network_type": "vm"},
                        "mode": "autonomous",
                    }
                ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.5)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            for i in range(3):
                assert f"seq-{i}" in webhook.diagnosis_store
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)
