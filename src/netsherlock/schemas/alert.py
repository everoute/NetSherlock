"""Alert-related Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ProblemType(str, Enum):
    """Types of network problems the agent can diagnose.

    This enum defines all recognized problem types that can trigger
    diagnosis workflows.
    """

    VM_NETWORK_LATENCY = "vm_network_latency"
    VM_NETWORK_DROP = "vm_network_drop"
    SYSTEM_NETWORK_LATENCY = "system_network_latency"
    SYSTEM_NETWORK_DROP = "system_network_drop"
    VHOST_OVERLOAD = "vhost_overload"
    OVS_SLOW_PATH = "ovs_slow_path"
    THROUGHPUT_DEGRADATION = "throughput_degradation"
    TCP_RETRANSMISSION = "tcp_retransmission"

    @classmethod
    def from_alert_name(cls, alert_name: str) -> "ProblemType | None":
        """Map alertname to problem type.

        Args:
            alert_name: Alert name from monitoring system

        Returns:
            ProblemType if mapping exists, None otherwise
        """
        mapping = {
            "VMNetworkLatency": cls.VM_NETWORK_LATENCY,
            "VMNetworkDrop": cls.VM_NETWORK_DROP,
            "HostNetworkHighLatency": cls.SYSTEM_NETWORK_LATENCY,
            "HostNetworkLoss": cls.SYSTEM_NETWORK_DROP,
            "VhostCPUHigh": cls.VHOST_OVERLOAD,
            "OVSUpcallHigh": cls.OVS_SLOW_PATH,
        }
        return mapping.get(alert_name)


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertSource(BaseModel):
    """Source information for an alert."""

    host: str = Field(..., description="Source host IP or hostname")
    vm_id: str | None = Field(default=None, description="VM UUID if applicable")
    interface: str | None = Field(default=None, description="Network interface")


class AlertTarget(BaseModel):
    """Target information for an alert."""

    host: str = Field(..., description="Target host IP or hostname")
    vm_id: str | None = Field(default=None, description="VM UUID if applicable")


class AlertMetrics(BaseModel):
    """Metrics associated with an alert."""

    latency_ms: float | None = Field(default=None, description="Latency in milliseconds")
    loss_rate: float | None = Field(default=None, description="Packet loss rate (0-1)")


class AlertPayload(BaseModel):
    """Alert payload from Grafana webhook or CLI input.

    This is the L1→L2 interface for passing alert information
    to the environment awareness layer.
    """

    alert_id: str = Field(..., description="Unique alert identifier")
    alert_name: str = Field(..., description="Alert name/title")
    severity: AlertSeverity = Field(default=AlertSeverity.WARNING)
    source: AlertSource = Field(..., description="Alert source information")
    target: AlertTarget | None = Field(default=None, description="Alert target if applicable")
    metrics: AlertMetrics = Field(default_factory=AlertMetrics)
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = {"extra": "allow"}


class DiagnosisRequest(BaseModel):
    """Request to diagnose a network issue.

    Can be created from an alert or from CLI input.

    Parameters:
        network_type: Type of network to diagnose (vm or system)
        src_host: Source host management IP (required)
        src_vm: Source VM UUID (required for network_type=vm)
        dst_host: Destination host management IP (optional, for inter-node diagnosis)
        dst_vm: Destination VM UUID (required when dst_host is specified for vm network)

    Validation rules for VM network:
        - src_vm is required
        - If dst_host is specified, dst_vm must also be specified
        - If dst_vm is specified, dst_host must also be specified
    """

    request_id: str = Field(..., description="Unique request identifier")
    request_type: Literal["latency", "packet_drop", "connectivity"] = Field(
        ..., description="Type of diagnosis"
    )
    network_type: Literal["vm", "system"] = Field(
        ..., description="Network type: vm (VM network) or system (host network)"
    )
    src_host: str = Field(..., description="Source host management IP")
    src_vm: str | None = Field(
        default=None,
        description="Source VM UUID (required for network_type=vm)",
    )
    dst_host: str | None = Field(
        default=None,
        description="Destination host management IP (for inter-node diagnosis)",
    )
    dst_vm: str | None = Field(
        default=None,
        description="Destination VM UUID (required when dst_host specified for vm network)",
    )
    alert: AlertPayload | None = Field(
        default=None, description="Original alert if triggered by webhook"
    )
    alert_type: str | None = Field(
        default=None,
        description="Alert type for mode selection (e.g., VMNetworkLatency)",
    )
    options: dict = Field(default_factory=dict, description="Additional diagnosis options")

    model_config = {"extra": "allow"}

    def model_post_init(self, __context) -> None:
        """Validate parameter combinations after model initialization."""
        # VM network validation
        if self.network_type == "vm":
            if not self.src_vm:
                raise ValueError("--src-vm is required for network-type=vm")
            if self.dst_host and not self.dst_vm:
                raise ValueError("--dst-vm is required when --dst-host is specified")
            if self.dst_vm and not self.dst_host:
                raise ValueError("--dst-host is required when --dst-vm is specified")
