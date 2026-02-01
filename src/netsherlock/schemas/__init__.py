"""Schemas module - Pydantic models for data interfaces.

This module contains all the data models used across the application layers:
- Alert schemas (L1 input)
- Request schemas (unified diagnosis request)
- Result schemas (unified diagnosis result)
- Environment schemas (L2 output)
- Measurement schemas (L3 output)
- Report schemas (L4 output)
- Config schemas (application configuration)
"""

from .alert import (
    AlertMetrics,
    AlertPayload,
    AlertSeverity,
    AlertSource,
    AlertTarget,
    ProblemType,
)
from .config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
    InteractiveConfig,
)
from .environment import (
    FlowInfo,
    NetworkEndpoint,
    NetworkPath,
    NetworkType,
    PathSegment,
    PhysicalNIC,
    SystemNetworkEnv,
    SystemNetworkInfo,
    VhostInfo,
    VMNetworkEnv,
    VMNicInfo,
)
from .measurement import (
    CoordinatedMeasurementResult,
    DropPoint,
    LatencyBreakdown,
    LatencySegment,
    MeasurementMetadata,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
    PacketDropResult,
)
from .report import (
    DiagnosisReport,
    DiagnosisSummary,
    DropAnalysis,
    Finding,
    LatencyAnalysis,
    Recommendation,
    RootCause,
    RootCauseCategory,
    SegmentAttribution,
    Severity,
)
from .request import DiagnosisRequest
from .result import DiagnosisResult, DiagnosisStatus

__all__ = [
    # Alert schemas
    "AlertMetrics",
    "AlertPayload",
    "AlertSeverity",
    "AlertSource",
    "AlertTarget",
    "ProblemType",
    # Request schemas
    "DiagnosisRequest",
    # Result schemas
    "DiagnosisResult",
    "DiagnosisStatus",
    # Config schemas
    "AutonomousConfig",
    "CheckpointType",
    "DiagnosisConfig",
    "DiagnosisMode",
    "DiagnosisRequestSource",
    "InteractiveConfig",
    # Environment schemas
    "FlowInfo",
    "NetworkEndpoint",
    "NetworkPath",
    "NetworkType",
    "PathSegment",
    "PhysicalNIC",
    "SystemNetworkEnv",
    "SystemNetworkInfo",
    "VhostInfo",
    "VMNetworkEnv",
    "VMNicInfo",
    # Measurement schemas
    "CoordinatedMeasurementResult",
    "DropPoint",
    "LatencyBreakdown",
    "LatencySegment",
    "MeasurementMetadata",
    "MeasurementResult",
    "MeasurementStatus",
    "MeasurementType",
    "PacketDropResult",
    # Report schemas
    "DiagnosisReport",
    "DiagnosisSummary",
    "DropAnalysis",
    "Finding",
    "LatencyAnalysis",
    "Recommendation",
    "RootCause",
    "RootCauseCategory",
    "SegmentAttribution",
    "Severity",
]
