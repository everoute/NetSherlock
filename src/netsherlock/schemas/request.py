"""Unified diagnosis request model.

Consolidates the three request representations:
- schemas/alert.py DiagnosisRequest (CLI path)
- api/webhook.py DiagnosticRequest (webhook path)
- Raw dict (orchestrator/agent path)

into a single DiagnosisRequest used by all entry points.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from .alert import AlertPayload
from .config import DiagnosisMode, DiagnosisRequestSource


class DiagnosisRequest(BaseModel):
    """Unified diagnosis request — CLI, Webhook, and Orchestrator share this type.

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

    # Core identification
    request_id: str = Field(
        default_factory=lambda: f"diag-{uuid.uuid4().hex[:16]}",
        description="Unique request identifier",
    )
    request_type: Literal["latency", "packet_drop", "connectivity"] = Field(
        ..., description="Type of diagnosis"
    )
    network_type: Literal["vm", "system"] = Field(
        ..., description="Network type: vm (VM network) or system (host network)"
    )

    # Source node (required)
    src_host: str = Field(..., description="Source host management IP")
    src_vm: str | None = Field(
        default=None,
        description="Source VM UUID (required for network_type=vm)",
    )

    # Destination node (optional, for cross-node diagnosis)
    dst_host: str | None = Field(
        default=None,
        description="Destination host management IP (for inter-node diagnosis)",
    )
    dst_vm: str | None = Field(
        default=None,
        description="Destination VM UUID (required when dst_host specified for vm network)",
    )

    # Request source and alert context
    source: DiagnosisRequestSource = Field(
        default=DiagnosisRequestSource.CLI,
        description="Where this request originated from",
    )
    alert: AlertPayload | None = Field(
        default=None, description="Original alert if triggered by webhook"
    )
    alert_type: str | None = Field(
        default=None,
        description="Alert type for mode selection (e.g., VMNetworkLatency)",
    )

    # Runtime options
    mode: DiagnosisMode | None = Field(
        default=None,
        description="Requested diagnosis mode (None = determined by config)",
    )
    options: dict[str, Any] = Field(
        default_factory=dict, description="Additional diagnosis options"
    )
    description: str | None = Field(
        default=None, description="Human-readable description of the issue"
    )

    model_config = {"extra": "allow"}

    def model_post_init(self, __context: object) -> None:
        """Validate parameter combinations after model initialization."""
        if self.network_type == "vm":
            if not self.src_vm:
                raise ValueError("--src-vm is required for network-type=vm")
            if self.dst_host and not self.dst_vm:
                raise ValueError("--dst-vm is required when --dst-host is specified")
            if self.dst_vm and not self.dst_host:
                raise ValueError("--dst-host is required when --dst-vm is specified")
