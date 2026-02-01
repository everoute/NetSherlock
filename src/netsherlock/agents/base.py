"""
Base agent definitions and common utilities for the network troubleshooting system.

NOTE: This module maintains backward compatibility with legacy dataclass types.
New code should prefer importing from netsherlock.schemas instead.

Canonical types are now defined in schemas/:
- ProblemType -> schemas.alert.ProblemType
- RootCauseCategory -> schemas.report.RootCauseCategory
- FlowInfo -> schemas.environment.FlowInfo
- Recommendation -> schemas.report.Recommendation
- RootCause -> schemas.report.RootCause
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Re-export canonical types from schemas
from netsherlock.schemas.alert import ProblemType
from netsherlock.schemas.environment import FlowInfo
from netsherlock.schemas.report import (
    Recommendation,
    RootCause,
    RootCauseCategory,
)

# Legacy dataclass types below - kept for backward compatibility
# New code should use Pydantic models from schemas/ instead


@dataclass
class AlertContext:
    """Context extracted from an incoming alert.

    NOTE: Consider using schemas.alert.AlertPayload for new code.
    """

    alertname: str
    instance: str
    severity: str = "warning"
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    @property
    def node_ip(self) -> str:
        """Extract node IP from instance label."""
        return self.instance.split(":")[0] if self.instance else ""

    @property
    def problem_type(self) -> ProblemType | None:
        """Map alertname to problem type."""
        return ProblemType.from_alert_name(self.alertname)


@dataclass
class VMInfo:
    """VM information collected by L2.

    NOTE: Consider using schemas.environment.VMNetworkEnv for new code.
    """

    uuid: str
    name: str
    qemu_pid: int
    vhost_tids: list[int]
    vcpu_count: int = 0
    memory_mb: int = 0


@dataclass
class NetworkInfo:
    """Network topology information collected by L2.

    NOTE: Consider using schemas.environment.VMNicInfo for new code.
    """

    vnet: str = ""
    mac: str = ""
    ovs_bridge: str = ""
    ovs_port: str = ""
    ofport: int = 0
    phy_nic: str = ""
    bond_members: list[str] = field(default_factory=list)
    ip_address: str = ""
    mtu: int = 1500


@dataclass
class NodeEnvironment:
    """Environment information for a single node."""

    node_ip: str
    hostname: str = ""
    vm: VMInfo | None = None
    network: NetworkInfo = field(default_factory=NetworkInfo)
    ssh_user: str = "root"
    ssh_key_path: str = ""


@dataclass
class NetworkPath:
    """Network path between source and destination.

    NOTE: Consider using schemas.environment.NetworkPath for new code.
    """

    path_type: str  # "vm_to_vm", "system_to_system", "vm_to_system"
    same_host: bool
    segments: list[dict[str, str]]
    tunnel_type: str = "none"  # "vxlan", "gre", "none"


@dataclass
class NetworkEnvironment:
    """Complete network environment for measurements (L2 output)."""

    problem_type: ProblemType
    measurement_type: str
    source: NodeEnvironment
    destination: NodeEnvironment | None = None
    path: NetworkPath | None = None
    flow: FlowInfo | None = None


@dataclass
class LatencyHistogram:
    """Latency histogram statistics.

    NOTE: Consider using schemas.measurement.LatencyBreakdown for new code.
    """

    p50_us: float
    p95_us: float
    p99_us: float
    max_us: float
    samples: int = 0


@dataclass
class LatencySegment:
    """A single latency segment measurement.

    NOTE: Consider using schemas.measurement.LatencySegment for new code.
    """

    name: str
    layer: str  # "vm_internal", "vhost_processing", "host_internal", "physical_network"
    description: str = ""
    histogram: LatencyHistogram | None = None


@dataclass
class MeasurementResult:
    """Measurement results from L3.

    NOTE: Consider using schemas.measurement.MeasurementResult for new code.
    """

    measurement_id: str
    measurement_type: str
    timestamp: str
    duration_seconds: float
    sample_count: int
    segments: list[LatencySegment]
    total_latency: LatencyHistogram | None = None
    environment_summary: dict[str, Any] = field(default_factory=dict)
    raw_data_path: str = ""



# DiagnosisResult has been moved to schemas/result.py.
# Import from netsherlock.schemas.result instead.

__all__ = [
    # Canonical types (from schemas)
    "ProblemType",
    "RootCauseCategory",
    "FlowInfo",
    "Recommendation",
    "RootCause",
    # Legacy dataclass types (backward compatibility)
    "AlertContext",
    "VMInfo",
    "NetworkInfo",
    "NodeEnvironment",
    "NetworkPath",
    "NetworkEnvironment",
    "LatencyHistogram",
    "LatencySegment",
    "MeasurementResult",
]
