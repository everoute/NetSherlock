"""Measurement-related Pydantic models for L3 layer.

These schemas define the measurement results from BPF tools
and coordinated measurements.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MeasurementStatus(str, Enum):
    """Status of a measurement operation."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some data collected but incomplete
    FAILED = "failed"


class MeasurementType(str, Enum):
    """Type of measurement performed."""

    LATENCY = "latency"
    PACKET_DROP = "packet_drop"
    THROUGHPUT = "throughput"


class LatencySegment(BaseModel):
    """Latency measurement for a single network segment."""

    name: str = Field(..., description="Segment name (e.g., 'virtio_tx', 'ovs_flow')")
    avg_us: float = Field(..., description="Average latency in microseconds")
    p50_us: float = Field(default=0.0, description="P50 latency in microseconds")
    p95_us: float = Field(default=0.0, description="P95 latency in microseconds")
    p99_us: float = Field(default=0.0, description="P99 latency in microseconds")
    max_us: float = Field(default=0.0, description="Maximum latency in microseconds")
    min_us: float = Field(default=0.0, description="Minimum latency in microseconds")
    sample_count: int = Field(default=0, description="Number of samples")


class DropPoint(BaseModel):
    """Packet drop information at a specific kernel location."""

    location: str = Field(..., description="Kernel function/location")
    count: int = Field(..., description="Number of drops")
    stack: str = Field(default="", description="Kernel stack trace")
    reason: str = Field(default="", description="Drop reason if known")


class LatencyBreakdown(BaseModel):
    """Complete latency breakdown across all segments.

    This follows the 13-segment model for VM network latency:
    A: Application → virtio-net
    B: virtio-net TX queue
    C: vhost-net processing
    D: TAP device
    E: OVS flow processing
    F: Physical NIC TX
    G: Wire (network)
    H: Physical NIC RX
    I: OVS flow processing (RX)
    J: TAP device (RX)
    K: vhost-net processing (RX)
    L: virtio-net RX queue
    M: virtio-net → Application
    """

    segments: list[LatencySegment] = Field(
        default_factory=list, description="Latency by segment"
    )
    total_avg_us: float = Field(default=0.0, description="Total average latency")
    total_p99_us: float = Field(default=0.0, description="Total P99 latency")
    timestamp: datetime = Field(default_factory=datetime.now)


class PacketDropResult(BaseModel):
    """Result of packet drop monitoring."""

    drop_points: list[DropPoint] = Field(
        default_factory=list, description="Drop locations and counts"
    )
    total_drops: int = Field(default=0, description="Total drops observed")
    duration_sec: float = Field(default=0.0, description="Monitoring duration")
    timestamp: datetime = Field(default_factory=datetime.now)


class MeasurementMetadata(BaseModel):
    """Metadata about a measurement execution."""

    tool_name: str = Field(..., description="Name of the measurement tool")
    tool_version: str = Field(default="", description="Tool version")
    host: str = Field(..., description="Host where measurement was taken")
    duration_sec: float = Field(..., description="Measurement duration")
    sample_count: int = Field(default=0, description="Number of samples collected")
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = Field(default=None)


class MeasurementResult(BaseModel):
    """Generic measurement result.

    This is the L3→L4 interface containing measurement data
    for analysis.
    """

    measurement_id: str = Field(..., description="Unique measurement identifier")
    measurement_type: MeasurementType = Field(..., description="Type of measurement")
    status: MeasurementStatus = Field(..., description="Measurement status")
    error: str | None = Field(default=None, description="Error message if failed")

    # Type-specific data (one will be populated based on type)
    latency_data: LatencyBreakdown | None = Field(default=None)
    drop_data: PacketDropResult | None = Field(default=None)

    metadata: MeasurementMetadata = Field(..., description="Measurement metadata")
    raw_output: str = Field(default="", description="Raw tool output for debugging")

    model_config = {"extra": "allow"}


class CoordinatedMeasurementResult(BaseModel):
    """Result of a coordinated sender/receiver measurement."""

    measurement_id: str = Field(..., description="Unique identifier")
    receiver_result: MeasurementResult = Field(..., description="Receiver measurement")
    sender_result: MeasurementResult = Field(..., description="Sender measurement")

    # Combined analysis
    round_trip_us: float | None = Field(default=None, description="Round-trip time if available")
    one_way_us: float | None = Field(default=None, description="One-way latency if available")

    model_config = {"extra": "allow"}
