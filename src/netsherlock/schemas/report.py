"""Report-related Pydantic models for L4 layer.

These schemas define the diagnosis report structure and analysis results.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity level for findings."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class RootCauseCategory(str, Enum):
    """Categories for root cause classification."""

    VM_INTERNAL = "vm_internal"  # virtio/kernel stack issues
    HOST_INTERNAL = "host_internal"  # OVS/bridge issues
    VHOST_PROCESSING = "vhost_processing"  # vhost-net issues
    PHYSICAL_NETWORK = "physical_network"  # NIC/wire/switch issues
    CONFIGURATION = "configuration"  # Misconfiguration
    RESOURCE_CONTENTION = "resource_contention"  # CPU/memory/queue contention
    UNKNOWN = "unknown"


class SegmentAttribution(BaseModel):
    """Latency attribution for a network layer."""

    layer: str = Field(..., description="Layer name")
    segments: list[str] = Field(default_factory=list, description="Segment names in this layer")
    latency_us: float = Field(..., description="Total latency in this layer (us)")
    percentage: float = Field(..., description="Percentage of total latency")
    is_anomaly: bool = Field(default=False, description="Whether this layer has anomalous latency")


class Finding(BaseModel):
    """A single analysis finding or observation."""

    severity: Severity = Field(..., description="Finding severity")
    category: RootCauseCategory = Field(..., description="Root cause category")
    title: str = Field(..., description="Short title")
    description: str = Field(..., description="Detailed description")
    evidence: str = Field(default="", description="Supporting evidence/data")
    recommendation: str = Field(default="", description="Recommended action")


class LatencyAnalysis(BaseModel):
    """Result of latency segment analysis."""

    attributions: list[SegmentAttribution] = Field(
        default_factory=list, description="Latency by layer"
    )
    anomalous_segments: list[str] = Field(
        default_factory=list, description="Segments with anomalous latency"
    )
    total_latency_us: float = Field(default=0.0, description="Total measured latency")
    baseline_latency_us: float | None = Field(
        default=None, description="Expected baseline latency"
    )
    excess_latency_us: float | None = Field(
        default=None, description="Latency above baseline"
    )


class DropAnalysis(BaseModel):
    """Result of packet drop analysis."""

    total_drops: int = Field(default=0, description="Total drops observed")
    drop_rate: float = Field(default=0.0, description="Drop rate (0-1)")
    top_drop_locations: list[str] = Field(
        default_factory=list, description="Top kernel drop locations"
    )
    likely_causes: list[str] = Field(
        default_factory=list, description="Likely causes for drops"
    )


class RootCause(BaseModel):
    """Root cause determination from diagnosis.

    Represents the identified root cause with confidence level
    and supporting evidence.
    """

    category: RootCauseCategory = Field(..., description="Root cause category")
    component: str = Field(..., description="Specific component/layer affected")
    confidence: float = Field(
        ..., ge=0, le=1, description="Confidence level (0-1)"
    )
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence")
    contributing_factors: list[str] = Field(
        default_factory=list, description="Additional contributing factors"
    )


class Recommendation(BaseModel):
    """Action recommendation from diagnosis.

    Describes a recommended action to address the identified issue.
    """

    priority: int = Field(..., ge=1, description="Priority (1=highest)")
    action: str = Field(..., description="Recommended action description")
    command: str = Field(default="", description="Optional command to execute")
    metric: str = Field(default="", description="Metric to monitor for improvement")
    rationale: str = Field(default="", description="Why this action is recommended")


class DiagnosisSummary(BaseModel):
    """High-level summary of diagnosis."""

    status: Literal["healthy", "degraded", "critical"] = Field(
        ..., description="Overall network health status"
    )
    primary_issue: str | None = Field(default=None, description="Primary issue identified")
    root_cause: RootCauseCategory = Field(
        default=RootCauseCategory.UNKNOWN, description="Primary root cause category"
    )
    confidence: float = Field(default=0.0, description="Confidence in diagnosis (0-1)")


class DiagnosisReport(BaseModel):
    """Complete network diagnosis report.

    This is the final output of the L4 analysis layer.
    """

    # Identification
    report_id: str = Field(..., description="Unique report identifier")
    request_id: str = Field(..., description="Original request ID")
    generated_at: datetime = Field(default_factory=datetime.now)

    # Context
    source_host: str = Field(..., description="Primary host diagnosed")
    target_host: str | None = Field(default=None, description="Target host if applicable")
    vm_id: str | None = Field(default=None, description="VM UUID if VM diagnosis")
    diagnosis_type: str = Field(..., description="Type of diagnosis performed")

    # Summary
    summary: DiagnosisSummary = Field(..., description="High-level summary")

    # Analysis results
    latency_analysis: LatencyAnalysis | None = Field(default=None)
    drop_analysis: DropAnalysis | None = Field(default=None)

    # Findings
    findings: list[Finding] = Field(default_factory=list, description="All findings")

    # Recommendations
    recommendations: list[str] = Field(
        default_factory=list, description="Prioritized recommendations"
    )

    # Metadata
    measurement_duration_sec: float = Field(default=0.0)
    total_analysis_time_sec: float = Field(default=0.0)

    # Raw data reference
    raw_measurements: dict = Field(
        default_factory=dict, description="Reference to raw measurement data"
    )

    model_config = {"extra": "allow"}

    def to_markdown(self) -> str:
        """Generate markdown-formatted report."""
        lines = [
            f"# Network Diagnosis Report",
            f"",
            f"**Report ID**: {self.report_id}",
            f"**Generated**: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Host**: {self.source_host}",
        ]

        if self.vm_id:
            lines.append(f"**VM**: {self.vm_id}")
        if self.target_host:
            lines.append(f"**Target**: {self.target_host}")

        lines.extend([
            f"",
            f"## Summary",
            f"",
            f"- **Status**: {self.summary.status.upper()}",
            f"- **Primary Issue**: {self.summary.primary_issue or 'None identified'}",
            f"- **Root Cause**: {self.summary.root_cause.value}",
            f"- **Confidence**: {self.summary.confidence:.0%}",
        ])

        if self.latency_analysis:
            lines.extend([
                f"",
                f"## Latency Analysis",
                f"",
                f"Total latency: {self.latency_analysis.total_latency_us:.1f} µs",
                f"",
                f"| Layer | Latency (µs) | Percentage |",
                f"|-------|-------------|------------|",
            ])
            for attr in self.latency_analysis.attributions:
                flag = " ⚠️" if attr.is_anomaly else ""
                lines.append(
                    f"| {attr.layer}{flag} | {attr.latency_us:.1f} | {attr.percentage:.1%} |"
                )

        if self.drop_analysis and self.drop_analysis.total_drops > 0:
            lines.extend([
                f"",
                f"## Packet Drop Analysis",
                f"",
                f"Total drops: {self.drop_analysis.total_drops}",
                f"Drop rate: {self.drop_analysis.drop_rate:.2%}",
            ])

        if self.findings:
            lines.extend([
                f"",
                f"## Findings",
                f"",
            ])
            for finding in self.findings:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[finding.severity.value]
                lines.append(f"### {icon} {finding.title}")
                lines.append(f"")
                lines.append(finding.description)
                if finding.evidence:
                    lines.append(f"")
                    lines.append(f"**Evidence**: {finding.evidence}")
                if finding.recommendation:
                    lines.append(f"")
                    lines.append(f"**Recommendation**: {finding.recommendation}")
                lines.append(f"")

        if self.recommendations:
            lines.extend([
                f"## Recommendations",
                f"",
            ])
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. {rec}")

        return "\n".join(lines)
