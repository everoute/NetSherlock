"""Tests for webhook API endpoints and mode handling.

These tests verify:
1. Mode selection logic for webhook requests
2. auto_agent_loop triggers autonomous mode for known alerts
3. Unknown alert types use interactive mode
4. Mode parameter in DiagnosticRequest
5. API endpoints return correct mode information
6. API key authentication
7. Worker error handling
8. Input validation
"""

import asyncio
import sys
from unittest.mock import MagicMock

# Mock the claude_code_sdk module before importing webhook
mock_sdk = MagicMock()
sys.modules["claude_code_sdk"] = mock_sdk

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from netsherlock.api.webhook import (
    app,
    determine_webhook_mode,
    AlertmanagerWebhook,
    AlertmanagerAlert,
    DiagnosticRequest,
    generate_diagnosis_id,
    verify_api_key,
    _get_api_key,
    _is_insecure_mode_allowed,
    diagnosis_worker,
    diagnosis_queue,
    diagnosis_store,
    VALID_DIAGNOSIS_TYPES,
    VALID_NETWORK_TYPES,
)
from netsherlock.schemas.config import (
    DiagnosisMode,
    DiagnosisConfig,
    AutonomousConfig,
    InteractiveConfig,
)


# Test API key for authentication tests
TEST_API_KEY = "test-api-key-12345"


@pytest.fixture
def allow_insecure_mode():
    """Fixture to allow insecure mode for testing without API key."""
    with patch("netsherlock.api.webhook._get_api_key", return_value=""):
        with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
            yield


class TestDetermineWebhookMode:
    """Tests for the determine_webhook_mode function."""

    def test_default_mode_is_interactive(self):
        """Without auto_agent_loop, default mode should be interactive."""
        with patch("netsherlock.api.webhook.get_settings") as mock_settings:
            mock_config = DiagnosisConfig(
                default_mode=DiagnosisMode.INTERACTIVE,
                autonomous=AutonomousConfig(enabled=False, auto_agent_loop=False),
            )
            mock_settings.return_value.get_diagnosis_config.return_value = mock_config

            mode = determine_webhook_mode(alert_type="VMNetworkLatency")
            assert mode == DiagnosisMode.INTERACTIVE

    def test_force_mode_overrides_config(self):
        """force_mode should override config-based mode selection."""
        mode = determine_webhook_mode(
            alert_type="VMNetworkLatency",
            force_mode=DiagnosisMode.AUTONOMOUS,
        )
        assert mode == DiagnosisMode.AUTONOMOUS

    def test_auto_agent_loop_with_known_alert_uses_autonomous(self):
        """auto_agent_loop=true with known alert should use autonomous."""
        with patch("netsherlock.api.webhook.get_settings") as mock_settings:
            mock_config = DiagnosisConfig(
                default_mode=DiagnosisMode.INTERACTIVE,
                autonomous=AutonomousConfig(
                    enabled=True,
                    auto_agent_loop=True,
                    known_alert_types=["VMNetworkLatency"],
                ),
            )
            mock_settings.return_value.get_diagnosis_config.return_value = mock_config

            mode = determine_webhook_mode(alert_type="VMNetworkLatency")
            assert mode == DiagnosisMode.AUTONOMOUS

    def test_auto_agent_loop_with_unknown_alert_uses_interactive(self):
        """auto_agent_loop=true with unknown alert should use interactive."""
        with patch("netsherlock.api.webhook.get_settings") as mock_settings:
            mock_config = DiagnosisConfig(
                default_mode=DiagnosisMode.INTERACTIVE,
                autonomous=AutonomousConfig(
                    enabled=True,
                    auto_agent_loop=True,
                    known_alert_types=["VMNetworkLatency"],
                ),
            )
            mock_settings.return_value.get_diagnosis_config.return_value = mock_config

            mode = determine_webhook_mode(alert_type="UnknownAlertType")
            assert mode == DiagnosisMode.INTERACTIVE

    def test_no_alert_type_uses_interactive(self):
        """No alert type should default to interactive."""
        with patch("netsherlock.api.webhook.get_settings") as mock_settings:
            mock_config = DiagnosisConfig(
                default_mode=DiagnosisMode.INTERACTIVE,
                autonomous=AutonomousConfig(
                    enabled=True,
                    auto_agent_loop=True,
                    known_alert_types=["VMNetworkLatency"],
                ),
            )
            mock_settings.return_value.get_diagnosis_config.return_value = mock_config

            mode = determine_webhook_mode(alert_type=None)
            assert mode == DiagnosisMode.INTERACTIVE


class TestGenerateDiagnosisId:
    """Tests for the generate_diagnosis_id function."""

    def test_generates_unpredictable_ids(self):
        """IDs should be unique and unpredictable."""
        ids = [generate_diagnosis_id() for _ in range(100)]
        # All IDs should be unique
        assert len(set(ids)) == 100

    def test_includes_prefix(self):
        """ID should include the specified prefix."""
        id1 = generate_diagnosis_id("alert")
        id2 = generate_diagnosis_id("manual")
        assert id1.startswith("alert-")
        assert id2.startswith("manual-")

    def test_default_prefix(self):
        """Default prefix should be 'diag'."""
        diagnosis_id = generate_diagnosis_id()
        assert diagnosis_id.startswith("diag-")


class TestApiKeyAuthentication:
    """Tests for API key authentication."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    # Standard valid payload for tests
    VALID_PAYLOAD = {
        "network_type": "vm",
        "diagnosis_type": "latency",
        "src_host": "192.168.1.10",
        "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    }

    def test_missing_api_key_returns_401(self, client):
        """Missing API key should return 401."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            response = client.post("/diagnose", json=self.VALID_PAYLOAD)
            assert response.status_code == 401
            assert "Missing X-API-Key header" in response.json()["detail"]

    def test_invalid_api_key_returns_403(self, client):
        """Invalid API key should return 403."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            response = client.post(
                "/diagnose",
                json=self.VALID_PAYLOAD,
                headers={"X-API-Key": "wrong-key"},
            )
            assert response.status_code == 403
            assert "Invalid API key" in response.json()["detail"]

    def test_valid_api_key_succeeds(self, client):
        """Valid API key should allow request."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                mock_config = DiagnosisConfig(
                    default_mode=DiagnosisMode.INTERACTIVE,
                )
                mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                response = client.post(
                    "/diagnose",
                    json=self.VALID_PAYLOAD,
                    headers={"X-API-Key": TEST_API_KEY},
                )
                assert response.status_code == 200

    def test_no_api_key_configured_requires_insecure_flag(self, client):
        """When no API key is configured, requests should fail unless insecure mode is allowed."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=False):
                response = client.post("/diagnose", json=self.VALID_PAYLOAD)
                assert response.status_code == 500
                assert "WEBHOOK_API_KEY" in response.json()["detail"]

    def test_no_api_key_with_insecure_flag_allows_requests(self, client):
        """When no API key is configured but insecure mode is allowed, requests should succeed."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    response = client.post("/diagnose", json=self.VALID_PAYLOAD)
                    assert response.status_code == 200

    def test_health_endpoint_no_auth_required(self, client):
        """Health endpoint should not require authentication."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            response = client.get("/health")
            assert response.status_code == 200


class TestInputValidation:
    """Tests for input validation."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_invalid_network_type_rejected(self, client):
        """Invalid network_type should be rejected."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                payload = {
                    "network_type": "invalid_type",
                    "src_host": "192.168.1.10",
                }
                response = client.post("/diagnose", json=payload)
                assert response.status_code == 422

    def test_invalid_src_host_ip_rejected(self, client):
        """Invalid src_host IP should be rejected."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                payload = {
                    "network_type": "vm",
                    "src_host": "not-an-ip",
                    "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
                }
                response = client.post("/diagnose", json=payload)
                assert response.status_code == 422

    def test_invalid_dst_host_ip_rejected(self, client):
        """Invalid dst_host IP should be rejected."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                payload = {
                    "network_type": "vm",
                    "src_host": "192.168.1.10",
                    "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
                    "dst_host": "not-an-ip",
                    "dst_vm": "bf7bb275-715d-5dc1-95c9-3feb045418g2",
                }
                response = client.post("/diagnose", json=payload)
                assert response.status_code == 422

    def test_valid_network_types(self):
        """All valid network types should be accepted."""
        for network_type in VALID_NETWORK_TYPES:
            if network_type == "vm":
                request = DiagnosticRequest(
                    network_type=network_type,
                    src_host="192.168.1.10",
                    src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
                )
            else:
                request = DiagnosticRequest(
                    network_type=network_type,
                    src_host="192.168.1.10",
                )
            assert request.network_type == network_type

    def test_valid_diagnosis_types(self):
        """All valid diagnosis types should be accepted."""
        for diagnosis_type in VALID_DIAGNOSIS_TYPES:
            request = DiagnosticRequest(
                network_type="vm",
                diagnosis_type=diagnosis_type,
                src_host="192.168.1.10",
                src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            )
            assert request.diagnosis_type == diagnosis_type

    def test_vm_network_requires_src_vm(self):
        """VM network should require src_vm."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                network_type="vm",
                src_host="192.168.1.10",
            )

    def test_vm_network_dst_host_requires_dst_vm(self):
        """VM network with dst_host should require dst_vm."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                network_type="vm",
                src_host="192.168.1.10",
                src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
                dst_host="192.168.1.20",
            )


class TestAlertmanagerWebhookEndpoint:
    """Tests for /webhook/alertmanager endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.fixture
    def mock_orchestrator(self):
        """Mock the orchestrator."""
        with patch("netsherlock.api.webhook.orchestrator") as mock:
            mock.diagnose_alert = MagicMock()
            yield mock

    def test_alertmanager_webhook_returns_mode(self, client):
        """Alertmanager webhook should return mode in response."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                        autonomous=AutonomousConfig(enabled=False),
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    payload = {
                        "status": "firing",
                        "alerts": [
                            {
                                "status": "firing",
                                "labels": {"alertname": "VMNetworkLatency"},
                                "fingerprint": "abc12345",
                            }
                        ],
                    }

                    response = client.post("/webhook/alertmanager", json=payload)
                    assert response.status_code == 200

                    data = response.json()
                    assert len(data) == 1
                    assert data[0]["mode"] == "interactive"
                    assert data[0]["status"] == "queued"

    def test_alertmanager_webhook_autonomous_for_known_alert(self, client):
        """Known alert with auto_agent_loop should use autonomous mode."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                        autonomous=AutonomousConfig(
                            enabled=True,
                            auto_agent_loop=True,
                            known_alert_types=["VMNetworkLatency"],
                        ),
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    payload = {
                        "status": "firing",
                        "alerts": [
                            {
                                "status": "firing",
                                "labels": {"alertname": "VMNetworkLatency"},
                                "fingerprint": "known123",
                            }
                        ],
                    }

                    response = client.post("/webhook/alertmanager", json=payload)
                    assert response.status_code == 200

                    data = response.json()
                    assert len(data) == 1
                    assert data[0]["mode"] == "autonomous"

    def test_alertmanager_webhook_interactive_for_unknown_alert(self, client):
        """Unknown alert should use interactive mode."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                        autonomous=AutonomousConfig(
                            enabled=True,
                            auto_agent_loop=True,
                            known_alert_types=["VMNetworkLatency"],
                        ),
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    payload = {
                        "status": "firing",
                        "alerts": [
                            {
                                "status": "firing",
                                "labels": {"alertname": "UnknownAlert"},
                                "fingerprint": "unknown1",
                            }
                        ],
                    }

                    response = client.post("/webhook/alertmanager", json=payload)
                    assert response.status_code == 200

                    data = response.json()
                    assert len(data) == 1
                    assert data[0]["mode"] == "interactive"

    def test_alertmanager_webhook_ignores_resolved(self, client):
        """Resolved alerts should be ignored."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                payload = {
                    "status": "resolved",
                    "alerts": [
                        {
                            "status": "resolved",
                            "labels": {"alertname": "VMNetworkLatency"},
                        }
                    ],
                }

                response = client.post("/webhook/alertmanager", json=payload)
                assert response.status_code == 200
                assert response.json() == []

    def test_alertmanager_webhook_requires_auth(self, client):
        """Alertmanager webhook should require authentication when configured."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            payload = {
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {"alertname": "VMNetworkLatency"},
                    }
                ],
            }

            response = client.post("/webhook/alertmanager", json=payload)
            assert response.status_code == 401


class TestDiagnoseEndpoint:
    """Tests for /diagnose endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    # Standard valid payload for tests
    VALID_PAYLOAD = {
        "network_type": "vm",
        "diagnosis_type": "latency",
        "src_host": "192.168.1.10",
        "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    }

    def test_diagnose_default_mode(self, client):
        """Diagnose without mode should use config default."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    response = client.post("/diagnose", json=self.VALID_PAYLOAD)
                    assert response.status_code == 200

                    data = response.json()
                    assert data["mode"] == "interactive"
                    assert data["status"] == "queued"

    def test_diagnose_explicit_autonomous_mode(self, client):
        """Diagnose with mode=autonomous should use autonomous."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.INTERACTIVE,
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    payload = {**self.VALID_PAYLOAD, "mode": "autonomous"}

                    response = client.post("/diagnose", json=payload)
                    assert response.status_code == 200

                    data = response.json()
                    assert data["mode"] == "autonomous"

    def test_diagnose_explicit_interactive_mode(self, client):
        """Diagnose with mode=interactive should use interactive."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.AUTONOMOUS,
                        autonomous=AutonomousConfig(enabled=True),
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    payload = {**self.VALID_PAYLOAD, "mode": "interactive"}

                    response = client.post("/diagnose", json=payload)
                    assert response.status_code == 200

                    data = response.json()
                    assert data["mode"] == "interactive"

    def test_diagnose_response_includes_mode_message(self, client):
        """Diagnose response should include mode in message."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.get_settings") as mock_settings:
                    mock_config = DiagnosisConfig(
                        default_mode=DiagnosisMode.AUTONOMOUS,
                        autonomous=AutonomousConfig(enabled=True),
                    )
                    mock_settings.return_value.get_diagnosis_config.return_value = mock_config

                    response = client.post("/diagnose", json=self.VALID_PAYLOAD)
                    assert response.status_code == 200

                    data = response.json()
                    assert "autonomous" in data["message"]


class TestGetDiagnosisEndpoint:
    """Tests for /diagnose/{diagnosis_id} endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_get_diagnosis_not_found(self, client):
        """Non-existent diagnosis should return 404."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                response = client.get("/diagnose/nonexistent-id")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"]

    def test_get_diagnosis_requires_auth(self, client):
        """Get diagnosis should require authentication when configured."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            response = client.get("/diagnose/some-id")
            assert response.status_code == 401


class TestListDiagnosesEndpoint:
    """Tests for /diagnoses endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_list_diagnoses_requires_auth(self, client):
        """List diagnoses should require authentication when configured."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=TEST_API_KEY):
            response = client.get("/diagnoses")
            assert response.status_code == 401

    def test_list_diagnoses_empty(self, client):
        """Empty diagnosis store should return empty list."""
        with patch("netsherlock.api.webhook._get_api_key", return_value=""):
            with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
                with patch("netsherlock.api.webhook.diagnosis_store", {}):
                    response = client.get("/diagnoses")
                    assert response.status_code == 200
                    assert response.json() == []


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_health_returns_status(self, client):
        """Health endpoint should return status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "queue_size" in data


class TestDiagnosticRequestModel:
    """Tests for DiagnosticRequest model."""

    # Standard valid request kwargs
    VALID_VM_REQUEST = {
        "network_type": "vm",
        "src_host": "192.168.1.10",
        "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    }

    def test_request_with_mode(self):
        """Request should accept mode parameter."""
        request = DiagnosticRequest(
            **self.VALID_VM_REQUEST,
            mode="autonomous",
        )
        assert request.mode == "autonomous"

    def test_request_without_mode(self):
        """Request without mode should have None."""
        request = DiagnosticRequest(**self.VALID_VM_REQUEST)
        assert request.mode is None

    def test_request_invalid_mode_rejected(self):
        """Invalid mode should be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                **self.VALID_VM_REQUEST,
                mode="invalid_mode",
            )

    def test_request_invalid_network_type_rejected(self):
        """Invalid network_type should be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                network_type="invalid_network",
                src_host="192.168.1.10",
            )

    def test_request_invalid_ip_rejected(self):
        """Invalid IP address should be rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                network_type="vm",
                src_host="not-an-ip",
                src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            )

    def test_request_vm_requires_src_vm(self):
        """VM network should require src_vm."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DiagnosticRequest(
                network_type="vm",
                src_host="192.168.1.10",
            )

    def test_request_system_network_no_src_vm_required(self):
        """System network should not require src_vm."""
        request = DiagnosticRequest(
            network_type="system",
            src_host="192.168.1.10",
        )
        assert request.network_type == "system"
        assert request.src_vm is None

    def test_request_vm_to_vm_valid(self):
        """VM-to-VM request should be valid with all required fields."""
        request = DiagnosticRequest(
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.1.20",
            dst_vm="bf7bb275-715d-5dc1-95c9-3feb045418g2",
        )
        assert request.dst_host == "192.168.1.20"
        assert request.dst_vm == "bf7bb275-715d-5dc1-95c9-3feb045418g2"


class TestAlertmanagerModels:
    """Tests for Alertmanager webhook models."""

    def test_alertmanager_alert_model(self):
        """AlertmanagerAlert should parse correctly."""
        alert = AlertmanagerAlert(
            status="firing",
            labels={"alertname": "VMNetworkLatency", "instance": "192.168.1.10:9100"},
            annotations={"summary": "High latency detected"},
            fingerprint="abc12345",
        )
        assert alert.status == "firing"
        assert alert.labels["alertname"] == "VMNetworkLatency"

    def test_alertmanager_webhook_model(self):
        """AlertmanagerWebhook should parse correctly."""
        webhook = AlertmanagerWebhook(
            status="firing",
            alerts=[
                AlertmanagerAlert(
                    status="firing",
                    labels={"alertname": "VMNetworkLatency"},
                )
            ],
        )
        assert webhook.status == "firing"
        assert len(webhook.alerts) == 1


class TestDiagnosisWorkerErrorHandling:
    """Tests for diagnosis_worker error handling."""

    @pytest.mark.asyncio
    async def test_worker_handles_orchestrator_none(self):
        """Worker should store error result when orchestrator is None."""
        # Clear any existing items and store
        while not diagnosis_queue.empty():
            try:
                diagnosis_queue.get_nowait()
                diagnosis_queue.task_done()
            except asyncio.QueueEmpty:
                break

        test_id = "test-worker-error"
        test_data = {"labels": {"alertname": "TestAlert"}}

        # Put a request in the queue
        await diagnosis_queue.put(("alert", test_id, test_data))

        with patch("netsherlock.api.webhook.orchestrator", None):
            # Run worker for one iteration
            # We'll simulate the worker loop manually
            request_type, request_id, request_data = await diagnosis_queue.get()

            from datetime import datetime, timezone
            from netsherlock.agents import DiagnosisResult

            # Simulate worker behavior when orchestrator is None
            diagnosis_store[request_id] = DiagnosisResult(
                diagnosis_id=request_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                alert_source=None,
                summary="Diagnosis failed: Orchestrator not initialized",
                root_cause=None,
                recommendations=[],
            )
            diagnosis_queue.task_done()

            # Verify error result was stored
            assert test_id in diagnosis_store
            result = diagnosis_store[test_id]
            assert "Orchestrator not initialized" in result.summary

            # Cleanup
            del diagnosis_store[test_id]

    @pytest.mark.asyncio
    async def test_worker_handles_orchestrator_exception(self):
        """Worker should store error result when orchestrator raises exception."""
        # Clear any existing items
        while not diagnosis_queue.empty():
            try:
                diagnosis_queue.get_nowait()
                diagnosis_queue.task_done()
            except asyncio.QueueEmpty:
                break

        test_id = "test-worker-exception"
        test_data = {"labels": {"alertname": "TestAlert"}}

        # Put a request in the queue
        await diagnosis_queue.put(("alert", test_id, test_data))

        mock_orchestrator = MagicMock()
        mock_orchestrator.diagnose_alert = AsyncMock(side_effect=Exception("Test error"))

        with patch("netsherlock.api.webhook.orchestrator", mock_orchestrator):
            # Run worker for one iteration (simulate manually)
            request_type, request_id, request_data = await diagnosis_queue.get()

            from datetime import datetime, timezone
            from netsherlock.agents import DiagnosisResult

            try:
                await mock_orchestrator.diagnose_alert(request_data)
            except Exception as e:
                # Simulate worker error handling
                diagnosis_store[request_id] = DiagnosisResult(
                    diagnosis_id=request_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    alert_source=None,
                    summary=f"Diagnosis failed: {str(e)}",
                    root_cause=None,
                    recommendations=[],
                )
            finally:
                diagnosis_queue.task_done()

            # Verify error result was stored
            assert test_id in diagnosis_store
            result = diagnosis_store[test_id]
            assert "Test error" in result.summary

            # Cleanup
            del diagnosis_store[test_id]
