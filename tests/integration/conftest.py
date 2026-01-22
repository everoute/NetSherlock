"""Shared fixtures for integration tests."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from netsherlock.config.settings import reset_settings
from netsherlock.controller.checkpoints import CheckpointManager
from netsherlock.controller.diagnosis_controller import DiagnosisController
from netsherlock.schemas.config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    InteractiveConfig,
)
from netsherlock.schemas.environment import VhostInfo, VMNetworkEnv, VMNicInfo
from netsherlock.schemas.measurement import (
    LatencyBreakdown,
    LatencySegment,
    MeasurementMetadata,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
)

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(filename: str) -> dict:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / filename) as f:
        return json.load(f)


# ============================================================
# Fixture Data Loaders
# ============================================================


@pytest.fixture
def alert_payloads():
    """Load alert payload fixtures."""
    return load_fixture("alert_payloads.json")


@pytest.fixture
def vm_network_env_data():
    """Load VM network environment fixtures."""
    return load_fixture("vm_network_env.json")


@pytest.fixture
def measurement_results_data():
    """Load measurement result fixtures."""
    return load_fixture("measurement_results.json")


@pytest.fixture
def grafana_responses():
    """Load Grafana response fixtures."""
    return load_fixture("grafana_responses.json")


# ============================================================
# Configuration Fixtures
# ============================================================


@pytest.fixture
def autonomous_config():
    """Create autonomous mode configuration."""
    return DiagnosisConfig(
        default_mode=DiagnosisMode.AUTONOMOUS,
        autonomous=AutonomousConfig(
            enabled=True,
            auto_agent_loop=True,
            interrupt_enabled=True,
            known_alert_types=["VMNetworkLatency", "HostNetworkLatency"],
        ),
        interactive=InteractiveConfig(
            checkpoints=[
                CheckpointType.PROBLEM_CLASSIFICATION,
                CheckpointType.MEASUREMENT_PLAN,
            ],
            timeout_seconds=300,
            auto_confirm_on_timeout=False,
        ),
    )


@pytest.fixture
def interactive_config():
    """Create interactive mode configuration."""
    return DiagnosisConfig(
        default_mode=DiagnosisMode.INTERACTIVE,
        autonomous=AutonomousConfig(
            enabled=True,
            auto_agent_loop=False,
            interrupt_enabled=True,
            known_alert_types=["VMNetworkLatency", "HostNetworkLatency"],
        ),
        interactive=InteractiveConfig(
            checkpoints=[
                CheckpointType.PROBLEM_CLASSIFICATION,
                CheckpointType.MEASUREMENT_PLAN,
            ],
            timeout_seconds=300,
            auto_confirm_on_timeout=False,
        ),
    )


@pytest.fixture
def auto_confirm_config():
    """Create config with auto-confirm on timeout."""
    return DiagnosisConfig(
        default_mode=DiagnosisMode.INTERACTIVE,
        autonomous=AutonomousConfig(enabled=True),
        interactive=InteractiveConfig(
            checkpoints=[CheckpointType.PROBLEM_CLASSIFICATION],
            timeout_seconds=30,
            auto_confirm_on_timeout=True,
        ),
    )


# ============================================================
# Environment Fixtures
# ============================================================


@pytest.fixture
def sample_vm_env(vm_network_env_data):
    """Create a sample VMNetworkEnv from fixture data."""
    data = vm_network_env_data["vm_network_env_sample"]
    return VMNetworkEnv(
        vm_uuid=data["vm_uuid"],
        host=data["host"],
        qemu_pid=data["qemu_pid"],
        nics=[
            VMNicInfo(
                mac=nic["mac"],
                host_vnet=nic["host_vnet"],
                ovs_bridge=nic["ovs_bridge"],
                vhost_pids=[
                    VhostInfo(pid=vhost["pid"], name=vhost.get("type", ""))
                    for vhost in nic.get("vhost_pids", [])
                ],
            )
            for nic in data["nics"]
        ],
    )


# ============================================================
# Measurement Fixtures
# ============================================================


@pytest.fixture
def sample_latency_result(measurement_results_data):
    """Create a sample latency measurement result."""
    data = measurement_results_data["latency_measurement_result"]
    return MeasurementResult(
        measurement_id=data["measurement_id"],
        measurement_type=MeasurementType.LATENCY,
        status=MeasurementStatus.SUCCESS,
        metadata=MeasurementMetadata(
            tool_name=data["metadata"]["tool_name"],
            host=data["metadata"]["host"],
            duration_sec=data["metadata"]["duration_sec"],
        ),
        latency_data=LatencyBreakdown(
            segments=[
                LatencySegment(
                    name=seg["name"],
                    avg_us=seg["avg_us"],
                    p99_us=seg["p99_us"],
                )
                for seg in data["latency_data"]["segments"]
            ],
            total_avg_us=data["latency_data"]["total_avg_us"],
            total_p99_us=data["latency_data"]["total_p99_us"],
        ),
        raw_output=data.get("raw_output"),
    )


@pytest.fixture
def sample_failed_result(measurement_results_data):
    """Create a sample failed measurement result."""
    data = measurement_results_data["failed_measurement_result"]
    return MeasurementResult(
        measurement_id=data["measurement_id"],
        measurement_type=MeasurementType.LATENCY,
        status=MeasurementStatus.FAILED,
        error=data["error"],
        metadata=MeasurementMetadata(
            tool_name="",
            host="192.168.1.10",
            duration_sec=0,
        ),
    )


# ============================================================
# Mock Fixtures
# ============================================================


@pytest.fixture
def mock_ssh_manager():
    """Create a mock SSH manager."""
    mock = MagicMock()
    mock.execute = MagicMock(return_value=MagicMock(
        success=True,
        stdout="command output",
        stderr="",
        exit_code=0,
    ))
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=None)
    return mock


@pytest.fixture
def mock_grafana_client(grafana_responses):
    """Create a mock Grafana client."""
    mock = MagicMock()

    # Mock metrics query
    metrics_response = grafana_responses["metrics_query_success"]
    mock.query_metrics = MagicMock(return_value=MagicMock(
        status=metrics_response["status"],
        result_type=metrics_response["result_type"],
        series=metrics_response["series"],
    ))

    # Mock logs query
    logs_response = grafana_responses["logs_query_success"]
    mock.query_logs = MagicMock(return_value=MagicMock(
        status=logs_response["status"],
        entries=logs_response["entries"],
    ))

    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=None)
    return mock


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    mock = AsyncMock()
    mock.diagnose_alert = AsyncMock()
    mock.diagnose_request = AsyncMock()
    return mock


@pytest.fixture
def mock_tool_executor():
    """Create a mock tool executor."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.get_available_tools = MagicMock(return_value=[
        "grafana_query_metrics",
        "loki_query_logs",
        "collect_vm_network_env",
        "execute_coordinated_measurement",
        "analyze_latency_segments",
    ])
    return mock


# ============================================================
# Controller Fixtures
# ============================================================


@pytest.fixture
def diagnosis_controller(interactive_config):
    """Create a diagnosis controller with interactive config."""
    return DiagnosisController(interactive_config)


@pytest.fixture
def autonomous_controller(autonomous_config):
    """Create a diagnosis controller with autonomous config."""
    return DiagnosisController(autonomous_config)


@pytest.fixture
def checkpoint_manager():
    """Create a checkpoint manager."""
    return CheckpointManager()


# ============================================================
# Settings Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_settings_fixture():
    """Reset settings before each test."""
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def mock_settings(monkeypatch):
    """Create mock settings for tests."""
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-api-key")
    monkeypatch.setenv("WEBHOOK_ALLOW_INSECURE", "true")
    monkeypatch.setenv("GRAFANA_BASE_URL", "http://test-grafana:3000")
    monkeypatch.setenv("GRAFANA_USERNAME", "test-user")
    monkeypatch.setenv("GRAFANA_PASSWORD", "test-password")
    reset_settings()
