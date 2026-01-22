"""Analysis result schemas for L4 diagnostic analysis.

This module defines the data structures for latency breakdown analysis
and LLM-based root cause analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


class LayerType(str, Enum):
    """Network layer types for attribution."""

    VM_KERNEL = "vm_kernel"  # VM internal kernel stack (A + F + G + H + M)
    HOST_OVS = "host_ovs"  # Host OVS/bridge forwarding (B + D + I + K)
    PHYSICAL_NETWORK = "physical_network"  # Wire/switch latency (C + J)
    VIRT_RX = "virt_rx"  # Virtualization RX path (E + L)
    VIRT_TX = "virt_tx"  # Virtualization TX path (B_1 + I_1)


@dataclass
class SegmentData:
    """Latency data for a single network segment.

    Attributes:
        name: Segment identifier (A, B, C, ..., M, B_1, I_1)
        value_us: Latency value in microseconds
        source: Data source tool/log file
        description: Human-readable description of the segment
    """

    name: str
    value_us: float
    source: str = ""
    description: str = ""

    @property
    def value_ms(self) -> float:
        """Get value in milliseconds."""
        return self.value_us / 1000.0


@dataclass
class LayerData:
    """Aggregated latency data for a network layer.

    Attributes:
        layer: Layer type
        total_us: Total latency for this layer in microseconds
        percentage: Percentage of total RTT
        segments: List of segments in this layer
    """

    layer: LayerType
    total_us: float
    percentage: float = 0.0
    segments: list[str] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        """Get total in milliseconds."""
        return self.total_us / 1000.0


@dataclass
class LatencyBreakdown:
    """Complete latency breakdown from measurement analysis.

    This is the output of Phase 1 (deterministic data calculation)
    in the two-phase L4 analysis.

    Attributes:
        total_rtt_us: Total round-trip time in microseconds
        segments: Dictionary of segment name to SegmentData
        layer_attribution: Dictionary of layer type to LayerData
        validation_error_pct: Validation error percentage
        timestamp: When the analysis was performed
    """

    total_rtt_us: float
    segments: dict[str, SegmentData] = field(default_factory=dict)
    layer_attribution: dict[LayerType, LayerData] = field(default_factory=dict)
    validation_error_pct: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_rtt_ms(self) -> float:
        """Get total RTT in milliseconds."""
        return self.total_rtt_us / 1000.0

    def get_segment(self, name: str) -> SegmentData | None:
        """Get segment data by name."""
        return self.segments.get(name)

    def get_layer(self, layer: LayerType) -> LayerData | None:
        """Get layer data by type."""
        return self.layer_attribution.get(layer)

    def get_primary_contributor(self) -> LayerType | None:
        """Get the layer with highest latency contribution.

        Returns:
            LayerType with highest percentage, or None if empty
        """
        if not self.layer_attribution:
            return None
        return max(self.layer_attribution.values(), key=lambda x: x.percentage).layer

    def calculate_layer_attribution(self) -> None:
        """Calculate layer attribution from segments.

        This populates layer_attribution based on segment data.
        """
        # Define segment to layer mapping
        layer_segments = {
            LayerType.VM_KERNEL: ["A", "F", "G", "H", "M"],
            LayerType.HOST_OVS: ["B", "D", "I", "K"],
            LayerType.PHYSICAL_NETWORK: ["C", "J", "C_J"],  # C+J often combined
            LayerType.VIRT_RX: ["E", "L"],
            LayerType.VIRT_TX: ["B_1", "I_1"],
        }

        for layer, segment_names in layer_segments.items():
            total = 0.0
            found_segments = []
            for seg_name in segment_names:
                if seg_name in self.segments:
                    total += self.segments[seg_name].value_us
                    found_segments.append(seg_name)

            percentage = (total / self.total_rtt_us * 100) if self.total_rtt_us > 0 else 0.0

            self.layer_attribution[layer] = LayerData(
                layer=layer,
                total_us=total,
                percentage=percentage,
                segments=found_segments,
            )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "total_rtt_us": self.total_rtt_us,
            "total_rtt_ms": self.total_rtt_ms,
            "segments": {
                name: {
                    "value_us": seg.value_us,
                    "value_ms": seg.value_ms,
                    "source": seg.source,
                    "description": seg.description,
                }
                for name, seg in self.segments.items()
            },
            "layer_attribution": {
                layer.value: {
                    "total_us": data.total_us,
                    "total_ms": data.total_ms,
                    "percentage": data.percentage,
                    "segments": data.segments,
                }
                for layer, data in self.layer_attribution.items()
            },
            "validation_error_pct": self.validation_error_pct,
            "primary_contributor": (
                self.get_primary_contributor().value
                if self.get_primary_contributor()
                else None
            ),
        }


@dataclass
class ProbableCause:
    """A probable cause identified by LLM analysis.

    Attributes:
        cause: Description of the probable cause
        confidence: Confidence level (0.0 to 1.0)
        evidence: Supporting evidence from measurements
        layer: Related network layer
    """

    cause: str
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    layer: LayerType | None = None


@dataclass
class Recommendation:
    """A recommendation from the analysis.

    Attributes:
        action: Recommended action
        priority: Priority level (high, medium, low)
        rationale: Reason for the recommendation
    """

    action: str
    priority: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""


@dataclass
class AnalysisResult:
    """Complete analysis result from L4 diagnostic.

    This combines Phase 1 (data calculation) and Phase 2 (LLM reasoning)
    results.

    Attributes:
        breakdown: Latency breakdown from Phase 1
        primary_contributor: Main latency contributor layer
        probable_causes: List of probable causes from LLM
        recommendations: List of recommendations
        confidence: Overall analysis confidence
        reasoning: LLM reasoning process (for debugging)
        timestamp: When the analysis was performed
    """

    breakdown: LatencyBreakdown
    primary_contributor: LayerType | None = None
    probable_causes: list[ProbableCause] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_breakdown(cls, breakdown: LatencyBreakdown) -> AnalysisResult:
        """Create initial result from breakdown (Phase 1 only).

        Args:
            breakdown: Latency breakdown from Phase 1

        Returns:
            AnalysisResult with breakdown only
        """
        return cls(
            breakdown=breakdown,
            primary_contributor=breakdown.get_primary_contributor(),
        )

    def add_probable_cause(
        self,
        cause: str,
        confidence: float = 0.0,
        evidence: list[str] | None = None,
        layer: LayerType | None = None,
    ) -> None:
        """Add a probable cause.

        Args:
            cause: Description of the cause
            confidence: Confidence level
            evidence: Supporting evidence
            layer: Related layer
        """
        self.probable_causes.append(
            ProbableCause(
                cause=cause,
                confidence=confidence,
                evidence=evidence or [],
                layer=layer,
            )
        )

    def add_recommendation(
        self,
        action: str,
        priority: Literal["high", "medium", "low"] = "medium",
        rationale: str = "",
    ) -> None:
        """Add a recommendation.

        Args:
            action: Recommended action
            priority: Priority level
            rationale: Reason for recommendation
        """
        self.recommendations.append(
            Recommendation(
                action=action,
                priority=priority,
                rationale=rationale,
            )
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "breakdown": self.breakdown.to_dict(),
            "primary_contributor": (
                self.primary_contributor.value if self.primary_contributor else None
            ),
            "probable_causes": [
                {
                    "cause": pc.cause,
                    "confidence": pc.confidence,
                    "evidence": pc.evidence,
                    "layer": pc.layer.value if pc.layer else None,
                }
                for pc in self.probable_causes
            ],
            "recommendations": [
                {
                    "action": r.action,
                    "priority": r.priority,
                    "rationale": r.rationale,
                }
                for r in self.recommendations
            ],
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
        }

    def summary(self) -> str:
        """Generate human-readable summary.

        Returns:
            Summary string
        """
        lines = []
        lines.append(f"Total RTT: {self.breakdown.total_rtt_us:.2f} us ({self.breakdown.total_rtt_ms:.3f} ms)")

        if self.primary_contributor:
            lines.append(f"Primary Contributor: {self.primary_contributor.value}")

        if self.probable_causes:
            lines.append("\nProbable Causes:")
            for i, pc in enumerate(self.probable_causes, 1):
                lines.append(f"  {i}. {pc.cause} (confidence: {pc.confidence:.0%})")

        if self.recommendations:
            lines.append("\nRecommendations:")
            for i, r in enumerate(self.recommendations, 1):
                lines.append(f"  {i}. [{r.priority.upper()}] {r.action}")

        return "\n".join(lines)
