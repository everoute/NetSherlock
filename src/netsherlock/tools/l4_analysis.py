"""L4 Layer Tools: Diagnostic Analysis.

MCP tools for analyzing measurement results, identifying root causes,
and generating diagnosis reports.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import structlog

from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.environment import NetworkPath
from netsherlock.schemas.measurement import (
    LatencyBreakdown,
    MeasurementResult,
    MeasurementStatus,
    PacketDropResult,
)
from netsherlock.schemas.report import (
    DiagnosisReport,
    DiagnosisSummary,
    DropAnalysis,
    Finding,
    LatencyAnalysis,
    RootCauseCategory,
    SegmentAttribution,
    Severity,
)

logger = structlog.get_logger(__name__)


# Default latency thresholds (in microseconds)
DEFAULT_THRESHOLDS = {
    "total_p99_warning": 1000,  # 1ms
    "total_p99_critical": 5000,  # 5ms
    "segment_anomaly_ratio": 2.0,  # 2x average is anomaly
    "vm_internal_baseline": 50,
    "host_internal_baseline": 100,
    "vhost_baseline": 200,
    "physical_network_baseline": 100,
}

# Layer definitions for attribution
LAYER_DEFINITIONS = {
    "vm_internal": {
        "segments": ["virtio_tx", "virtio_rx", "kernel_stack"],
        "description": "VM kernel and virtio driver processing",
    },
    "vhost_processing": {
        "segments": ["vhost_to_tap", "tap_to_vhost"],
        "description": "vhost-net thread processing",
    },
    "host_internal": {
        "segments": ["tap_to_ovs", "ovs_flow", "ovs_to_tap"],
        "description": "OVS datapath and bridge processing",
    },
    "physical_network": {
        "segments": ["nic_tx", "wire", "nic_rx"],
        "description": "Physical NIC and network wire",
    },
}


def analyze_latency_segments(
    breakdown: LatencyBreakdown,
    thresholds: dict | None = None,
) -> LatencyAnalysis:
    """Analyze latency breakdown and identify anomalies.

    This is an L4 layer tool for analyzing latency measurement results
    and identifying which network layers contribute most to latency.

    Args:
        breakdown: Latency breakdown from L3 measurement
        thresholds: Optional custom thresholds dict

    Returns:
        LatencyAnalysis with attribution and anomaly detection

    Example:
        >>> result = analyze_latency_segments(measurement.latency_data)
        >>> for attr in result.attributions:
        ...     print(f"{attr.layer}: {attr.latency_us}us ({attr.percentage:.0%})")
    """
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    log = logger.bind(segments=len(breakdown.segments))
    log.debug("analyzing_latency_segments")

    # Group segments by layer
    layer_latencies: dict[str, float] = {}
    layer_segments: dict[str, list[str]] = {}

    for segment in breakdown.segments:
        # Find which layer this segment belongs to
        layer_name = "other"
        for layer, config in LAYER_DEFINITIONS.items():
            if any(seg_pattern in segment.name.lower() for seg_pattern in config["segments"]):
                layer_name = layer
                break

        if layer_name not in layer_latencies:
            layer_latencies[layer_name] = 0.0
            layer_segments[layer_name] = []

        layer_latencies[layer_name] += segment.avg_us
        layer_segments[layer_name].append(segment.name)

    total = breakdown.total_avg_us or sum(layer_latencies.values())

    # Build attributions
    attributions = []
    anomalous_segments = []

    for layer, latency in sorted(layer_latencies.items(), key=lambda x: -x[1]):
        percentage = latency / total if total > 0 else 0

        # Check for anomaly
        baseline_key = f"{layer}_baseline"
        baseline = thresholds.get(baseline_key, 100)
        is_anomaly = latency > baseline * thresholds["segment_anomaly_ratio"]

        if is_anomaly:
            anomalous_segments.extend(layer_segments[layer])

        attributions.append(
            SegmentAttribution(
                layer=layer,
                segments=layer_segments[layer],
                latency_us=latency,
                percentage=percentage,
                is_anomaly=is_anomaly,
            )
        )

    # Calculate excess latency
    baseline_total = sum(
        thresholds.get(f"{layer}_baseline", 100) for layer in layer_latencies
    )
    excess = total - baseline_total if total > baseline_total else None

    log.info(
        "latency_analysis_complete",
        total_us=total,
        anomalous_layers=len([a for a in attributions if a.is_anomaly]),
    )

    return LatencyAnalysis(
        attributions=attributions,
        anomalous_segments=anomalous_segments,
        total_latency_us=total,
        baseline_latency_us=baseline_total,
        excess_latency_us=excess,
    )


def analyze_packet_drops(
    drop_result: PacketDropResult,
) -> DropAnalysis:
    """Analyze packet drop results and identify likely causes.

    Args:
        drop_result: Packet drop data from L3 measurement

    Returns:
        DropAnalysis with drop summary and likely causes
    """
    log = logger.bind(total_drops=drop_result.total_drops)
    log.debug("analyzing_packet_drops")

    # Sort drops by count
    sorted_drops = sorted(drop_result.drop_points, key=lambda x: -x.count)
    top_locations = [d.location for d in sorted_drops[:5]]

    # Identify likely causes based on drop locations
    likely_causes = []

    location_causes = {
        "nf_hook_slow": "Netfilter/iptables rules dropping packets",
        "tcp_v4_rcv": "TCP receive path congestion or invalid packets",
        "__netif_receive_skb_core": "NIC receive buffer overflow",
        "ip_rcv": "IP layer validation failures",
        "skb_queue_purge": "Socket buffer overflow",
        "__udp4_lib_rcv": "UDP port unreachable or buffer overflow",
        "dev_queue_xmit": "TX queue full or NIC driver issue",
    }

    for dp in drop_result.drop_points:
        for location_pattern, cause in location_causes.items():
            if location_pattern in dp.location and cause not in likely_causes:
                likely_causes.append(cause)

    # Calculate drop rate (rough estimate based on typical packet counts)
    # This would be more accurate with total packet count
    drop_rate = min(drop_result.total_drops / 10000, 1.0) if drop_result.total_drops > 0 else 0

    log.info("drop_analysis_complete", top_location=top_locations[0] if top_locations else "none")

    return DropAnalysis(
        total_drops=drop_result.total_drops,
        drop_rate=drop_rate,
        top_drop_locations=top_locations,
        likely_causes=likely_causes,
    )


def generate_diagnosis_report(
    request: DiagnosisRequest,
    env: NetworkPath | None,
    measurements: list[MeasurementResult],
    latency_analysis: LatencyAnalysis | None = None,
    drop_analysis: DropAnalysis | None = None,
) -> DiagnosisReport:
    """Generate comprehensive diagnosis report.

    This is the final L4 layer tool that synthesizes all analysis
    into a structured diagnosis report.

    Args:
        request: Original diagnosis request
        env: Network environment/path information
        measurements: All measurement results
        latency_analysis: Latency analysis results (optional)
        drop_analysis: Drop analysis results (optional)

    Returns:
        DiagnosisReport with findings and recommendations

    Example:
        >>> report = generate_diagnosis_report(
        ...     request=request,
        ...     env=network_path,
        ...     measurements=[measurement_result],
        ...     latency_analysis=latency_result
        ... )
        >>> print(report.to_markdown())
    """
    report_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()

    log = logger.bind(report_id=report_id, request_id=request.request_id)
    log.info("generating_diagnosis_report")

    findings: list[Finding] = []
    recommendations: list[str] = []

    # Analyze measurement success/failure
    failed_measurements = [m for m in measurements if m.status == MeasurementStatus.FAILED]
    if failed_measurements:
        findings.append(
            Finding(
                severity=Severity.WARNING,
                category=RootCauseCategory.UNKNOWN,
                title="Measurement Failures",
                description=f"{len(failed_measurements)} of {len(measurements)} measurements failed",
                evidence=", ".join(m.error or "unknown" for m in failed_measurements),
                recommendation="Check SSH connectivity and BPF tool availability",
            )
        )

    # Analyze latency if available
    primary_issue = None
    root_cause = RootCauseCategory.UNKNOWN
    confidence = 0.5

    if latency_analysis:
        # Check for anomalous layers
        anomalous = [a for a in latency_analysis.attributions if a.is_anomaly]

        if anomalous:
            worst = max(anomalous, key=lambda a: a.latency_us)
            primary_issue = f"High latency in {worst.layer} layer"
            root_cause = RootCauseCategory(worst.layer) if worst.layer in [e.value for e in RootCauseCategory] else RootCauseCategory.UNKNOWN
            confidence = 0.8

            findings.append(
                Finding(
                    severity=Severity.WARNING if worst.latency_us < 5000 else Severity.CRITICAL,
                    category=root_cause,
                    title=f"High {worst.layer.replace('_', ' ').title()} Latency",
                    description=f"{worst.layer} layer contributing {worst.percentage:.0%} of total latency ({worst.latency_us:.0f}µs)",
                    evidence=f"Segments: {', '.join(worst.segments)}",
                    recommendation=_get_layer_recommendation(worst.layer),
                )
            )

            recommendations.append(_get_layer_recommendation(worst.layer))

        # Check total latency
        if latency_analysis.excess_latency_us and latency_analysis.excess_latency_us > 1000:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    category=RootCauseCategory.UNKNOWN,
                    title="Elevated Total Latency",
                    description=f"Total latency {latency_analysis.total_latency_us:.0f}µs exceeds baseline by {latency_analysis.excess_latency_us:.0f}µs",
                    evidence=f"Baseline: {latency_analysis.baseline_latency_us:.0f}µs",
                )
            )

    # Analyze drops if available
    if drop_analysis and drop_analysis.total_drops > 0:
        severity = Severity.CRITICAL if drop_analysis.total_drops > 100 else Severity.WARNING

        if not primary_issue:
            primary_issue = f"Packet drops detected ({drop_analysis.total_drops} drops)"

        findings.append(
            Finding(
                severity=severity,
                category=RootCauseCategory.UNKNOWN,
                title="Packet Drops Detected",
                description=f"Observed {drop_analysis.total_drops} packet drops",
                evidence=f"Top locations: {', '.join(drop_analysis.top_drop_locations[:3])}",
                recommendation="Investigate top drop locations and check for resource exhaustion",
            )
        )

        if drop_analysis.likely_causes:
            for cause in drop_analysis.likely_causes[:2]:
                recommendations.append(cause)

    # Determine overall status
    status: Literal["healthy", "degraded", "critical"]
    if not findings:
        status = "healthy"
    elif any(f.severity == Severity.CRITICAL for f in findings):
        status = "critical"
    else:
        status = "degraded"

    # Calculate total measurement duration
    total_duration = sum(m.metadata.duration_sec for m in measurements)

    summary = DiagnosisSummary(
        status=status,
        primary_issue=primary_issue,
        root_cause=root_cause,
        confidence=confidence,
    )

    report = DiagnosisReport(
        report_id=report_id,
        request_id=request.request_id,
        source_host=request.src_host,
        target_host=request.dst_host,
        vm_id=request.src_vm,
        diagnosis_type=request.request_type,
        summary=summary,
        latency_analysis=latency_analysis,
        drop_analysis=drop_analysis,
        findings=findings,
        recommendations=recommendations[:5],  # Top 5 recommendations
        measurement_duration_sec=total_duration,
        total_analysis_time_sec=(datetime.now() - start_time).total_seconds(),
    )

    log.info(
        "diagnosis_report_generated",
        status=status,
        findings=len(findings),
        recommendations=len(recommendations),
    )

    return report


def _get_layer_recommendation(layer: str) -> str:
    """Get recommendation for a specific network layer."""
    recommendations = {
        "vm_internal": "Check VM CPU utilization and virtio driver version. Consider enabling multiqueue virtio if not already enabled.",
        "vhost_processing": "Check vhost thread CPU affinity and host CPU utilization. Consider adjusting vhost thread priority.",
        "host_internal": "Review OVS flow table size and datapath configuration. Check for megaflow cache misses.",
        "physical_network": "Check NIC queue configuration and interrupt affinity. Verify switch/network configuration.",
    }
    return recommendations.get(layer, "Investigate the affected layer for configuration issues.")


def identify_root_cause(
    latency_analysis: LatencyAnalysis | None,
    drop_analysis: DropAnalysis | None,
) -> tuple[RootCauseCategory, float, str]:
    """Identify the most likely root cause.

    Returns:
        Tuple of (category, confidence, explanation)
    """
    if latency_analysis and latency_analysis.anomalous_segments:
        # Find the layer with highest anomalous contribution
        anomalous = [a for a in latency_analysis.attributions if a.is_anomaly]
        if anomalous:
            worst = max(anomalous, key=lambda a: a.latency_us)

            # Map layer to category
            layer_to_category = {
                "vm_internal": RootCauseCategory.VM_INTERNAL,
                "vhost_processing": RootCauseCategory.VHOST_PROCESSING,
                "host_internal": RootCauseCategory.HOST_INTERNAL,
                "physical_network": RootCauseCategory.PHYSICAL_NETWORK,
            }

            category = layer_to_category.get(worst.layer, RootCauseCategory.UNKNOWN)
            confidence = min(worst.percentage + 0.3, 0.95)  # Higher confidence for higher contribution
            explanation = f"{worst.layer} layer shows {worst.percentage:.0%} of total latency"

            return category, confidence, explanation

    if drop_analysis and drop_analysis.total_drops > 0:
        # Analyze drop locations to determine category
        for location in drop_analysis.top_drop_locations:
            if "ovs" in location.lower() or "openvswitch" in location.lower():
                return RootCauseCategory.HOST_INTERNAL, 0.7, f"OVS-related drops at {location}"
            if "netfilter" in location.lower() or "nf_" in location.lower():
                return RootCauseCategory.CONFIGURATION, 0.7, f"Netfilter drops at {location}"
            if "dev_queue" in location.lower() or "qdisc" in location.lower():
                return RootCauseCategory.RESOURCE_CONTENTION, 0.7, f"Queue drops at {location}"

        return RootCauseCategory.UNKNOWN, 0.5, "Packet drops detected but cause unclear"

    return RootCauseCategory.UNKNOWN, 0.3, "Insufficient data for root cause determination"
