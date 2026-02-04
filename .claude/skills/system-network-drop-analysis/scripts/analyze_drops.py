#!/usr/bin/env python3
"""Analyze packet drops from system network measurements.

Main entry point for drop analysis skill.
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from parse_drops import DropEvent, DropStats, parse_log_file


def get_drop_location_name(drop_type: str, direction: str) -> str:
    """Get human-readable drop location name."""
    if direction == "rx":
        names = {
            "drop_0_1": "Receiver Inbound (phy→stack)",
            "drop_1_2": "Receiver Stack (no reply generated)",
            "drop_2_3": "Receiver Outbound (stack→phy)",
        }
    else:  # tx
        names = {
            "drop_0_1": "Sender Outbound (stack→phy)",
            "drop_1_2": "External (network or peer)",
            "drop_2_3": "Sender Inbound (phy→stack)",
        }
    return names.get(drop_type, "Unknown")


def get_layer_attribution(drop_type: str, direction: str) -> str:
    """Attribute drop to a layer: Sender / Receiver / Network."""
    if direction == "rx":
        # RX mode: drops are on receiver side
        if drop_type in ("drop_0_1", "drop_1_2", "drop_2_3"):
            return "Receiver Host"
    else:  # tx
        if drop_type == "drop_0_1":
            return "Sender Host"
        elif drop_type == "drop_1_2":
            return "Network"
        elif drop_type == "drop_2_3":
            return "Sender Host"
    return "Unknown"


def analyze_drop_patterns(events: list[DropEvent]) -> dict[str, Any]:
    """Analyze temporal patterns in drop events.

    Detects:
    - Burst drops (multiple drops within short interval)
    - Sporadic drops (isolated events)
    - Inter-drop intervals
    """
    if not events:
        return {
            "pattern": "none",
            "burst_count": 0,
            "sporadic_count": 0,
            "bursts": [],
            "avg_interval_ms": 0,
        }

    if len(events) == 1:
        return {
            "pattern": "single",
            "burst_count": 0,
            "sporadic_count": 1,
            "bursts": [],
            "avg_interval_ms": 0,
        }

    # Sort by timestamp
    sorted_events = sorted(events, key=lambda e: e.timestamp)

    # Calculate inter-drop intervals
    intervals = []
    for i in range(1, len(sorted_events)):
        delta = (sorted_events[i].timestamp - sorted_events[i-1].timestamp).total_seconds() * 1000
        intervals.append(delta)

    avg_interval = sum(intervals) / len(intervals) if intervals else 0

    # Detect bursts (drops within 100ms of each other)
    BURST_THRESHOLD_MS = 100
    bursts = []
    current_burst = [sorted_events[0]]

    for i in range(1, len(sorted_events)):
        if intervals[i-1] <= BURST_THRESHOLD_MS:
            current_burst.append(sorted_events[i])
        else:
            if len(current_burst) >= 2:
                bursts.append({
                    "start": current_burst[0].timestamp.isoformat(),
                    "end": current_burst[-1].timestamp.isoformat(),
                    "count": len(current_burst),
                    "duration_ms": (current_burst[-1].timestamp - current_burst[0].timestamp).total_seconds() * 1000,
                })
            current_burst = [sorted_events[i]]

    # Handle last burst
    if len(current_burst) >= 2:
        bursts.append({
            "start": current_burst[0].timestamp.isoformat(),
            "end": current_burst[-1].timestamp.isoformat(),
            "count": len(current_burst),
            "duration_ms": (current_burst[-1].timestamp - current_burst[0].timestamp).total_seconds() * 1000,
        })

    burst_drops = sum(b["count"] for b in bursts)
    sporadic_drops = len(events) - burst_drops

    # Determine overall pattern
    if burst_drops > sporadic_drops:
        pattern = "burst"
    elif sporadic_drops > 0 and burst_drops == 0:
        pattern = "sporadic"
    else:
        pattern = "mixed"

    return {
        "pattern": pattern,
        "burst_count": len(bursts),
        "sporadic_count": sporadic_drops,
        "bursts": bursts,
        "avg_interval_ms": round(avg_interval, 1),
    }


def compute_location_attribution(
    sender_stats: DropStats,
    receiver_stats: DropStats,
) -> dict[str, Any]:
    """Compute drop attribution by layer."""

    # Sender TX mode: drop_0_1 and drop_2_3 are sender internal, drop_1_2 is external
    sender_internal = sender_stats.drop_0_1 + sender_stats.drop_2_3
    sender_external = sender_stats.drop_1_2

    # Receiver RX mode: all drops are receiver internal
    receiver_internal = receiver_stats.drop_0_1 + receiver_stats.drop_1_2 + receiver_stats.drop_2_3

    total = sender_internal + sender_external + receiver_internal

    layers = []
    if sender_internal > 0:
        layers.append({
            "name": "Sender Host Internal",
            "drops": sender_internal,
            "percentage": round(sender_internal / total * 100, 1) if total > 0 else 0,
            "types": ["Outbound (stack→phy)", "Inbound (phy→stack)"],
        })

    if receiver_internal > 0:
        layers.append({
            "name": "Receiver Host Internal",
            "drops": receiver_internal,
            "percentage": round(receiver_internal / total * 100, 1) if total > 0 else 0,
            "types": ["Inbound (phy→stack)", "Stack processing", "Outbound (stack→phy)"],
        })

    if sender_external > 0:
        layers.append({
            "name": "Network / External",
            "drops": sender_external,
            "percentage": round(sender_external / total * 100, 1) if total > 0 else 0,
            "types": ["Wire loss", "Peer not responding"],
        })

    # Sort by drops (highest first)
    layers.sort(key=lambda x: x["drops"], reverse=True)

    return {
        "total_drops": total,
        "layers": layers,
    }


def generate_recommendations(
    attribution: dict,
    pattern_analysis: dict,
    sender_stats: DropStats,
    receiver_stats: DropStats,
) -> list[str]:
    """Generate diagnostic recommendations based on analysis."""
    recommendations = []

    total = attribution["total_drops"]
    if total == 0:
        recommendations.append("No drops detected - network path is stable")
        return recommendations

    # Check dominant layer
    if attribution["layers"]:
        top_layer = attribution["layers"][0]
        if top_layer["percentage"] > 50:
            if "Sender" in top_layer["name"]:
                recommendations.append(
                    f"Investigate Sender Host: {top_layer['drops']} drops ({top_layer['percentage']}%) - "
                    "check CPU load, memory pressure, NIC driver"
                )
            elif "Receiver" in top_layer["name"]:
                recommendations.append(
                    f"Investigate Receiver Host: {top_layer['drops']} drops ({top_layer['percentage']}%) - "
                    "check protocol stack, OVS datapath, NIC ring buffers"
                )
            elif "Network" in top_layer["name"]:
                recommendations.append(
                    f"Investigate Physical Network: {top_layer['drops']} drops ({top_layer['percentage']}%) - "
                    "check switch congestion, cable quality, MTU settings"
                )

    # Check pattern
    if pattern_analysis["pattern"] == "burst":
        recommendations.append(
            f"Burst drop pattern detected ({pattern_analysis['burst_count']} bursts) - "
            "likely transient congestion or resource exhaustion"
        )
    elif pattern_analysis["pattern"] == "sporadic":
        recommendations.append(
            "Sporadic drops detected - may indicate intermittent issues "
            "(flaky connection, occasional timeouts)"
        )

    # Check specific drop types
    if sender_stats.drop_1_2 > 0:
        recommendations.append(
            f"External drops: {sender_stats.drop_1_2} - peer may be unresponsive or network congested"
        )

    if receiver_stats.drop_1_2 > 0:
        recommendations.append(
            f"Stack no-reply: {receiver_stats.drop_1_2} - kernel failed to generate ICMP response "
            "(rate limiting, ICMP disabled, or resource exhaustion)"
        )

    return recommendations


def generate_markdown_report(report: dict) -> str:
    """Generate Markdown report from analysis data."""
    lines = []

    # Header
    lines.append("# System Network Drop Analysis Report")
    lines.append("")
    lines.append(f"**Measurement Directory**: `{report.get('measurement_dir', 'N/A')}`")
    lines.append(f"**Analysis Time**: {report.get('timestamp', 'N/A')}")
    lines.append("")

    # Summary
    summary = report.get("summary", {})
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Total Drops** | {summary.get('total_drops', 0)} |")
    lines.append(f"| **Drop Rate** | {summary.get('drop_rate_pct', 0):.2f}% |")
    lines.append(f"| **Total Flows** | {summary.get('total_flows', 0)} |")
    lines.append(f"| **Complete Flows** | {summary.get('complete_flows', 0)} |")
    lines.append("")

    # Location Attribution
    attribution = report.get("location_attribution", {})
    layers = attribution.get("layers", [])
    if layers:
        lines.append("## Drop Location Attribution")
        lines.append("")
        lines.append("| Layer | Drops | Percentage | Drop Types |")
        lines.append("|-------|-------|------------|------------|")
        for layer in layers:
            types_str = ", ".join(layer.get("types", []))
            lines.append(f"| {layer['name']} | **{layer['drops']}** | {layer['percentage']}% | {types_str} |")
        lines.append("")

    # Drop Breakdown by Type
    sender = report.get("sender_stats", {})
    receiver = report.get("receiver_stats", {})

    lines.append("## Drop Breakdown by Type")
    lines.append("")
    lines.append("### Sender Host (TX Mode)")
    lines.append("")
    lines.append("| Drop Type | Count | Description |")
    lines.append("|-----------|-------|-------------|")
    lines.append(f"| drop_0_1 | {sender.get('drop_0_1', 0)} | Outbound: stack → phy TX |")
    lines.append(f"| drop_1_2 | {sender.get('drop_1_2', 0)} | External: network or peer |")
    lines.append(f"| drop_2_3 | {sender.get('drop_2_3', 0)} | Inbound: phy RX → stack |")
    lines.append("")

    lines.append("### Receiver Host (RX Mode)")
    lines.append("")
    lines.append("| Drop Type | Count | Description |")
    lines.append("|-----------|-------|-------------|")
    lines.append(f"| drop_0_1 | {receiver.get('drop_0_1', 0)} | Inbound: phy RX → icmp_rcv |")
    lines.append(f"| drop_1_2 | {receiver.get('drop_1_2', 0)} | Stack: no reply generated |")
    lines.append(f"| drop_2_3 | {receiver.get('drop_2_3', 0)} | Outbound: ip_send_skb → phy TX |")
    lines.append("")

    # Pattern Analysis
    pattern = report.get("pattern_analysis", {})
    lines.append("## Pattern Analysis")
    lines.append("")
    lines.append(f"- **Pattern Type**: {pattern.get('pattern', 'N/A')}")
    lines.append(f"- **Burst Events**: {pattern.get('burst_count', 0)}")
    lines.append(f"- **Sporadic Events**: {pattern.get('sporadic_count', 0)}")
    lines.append(f"- **Average Interval**: {pattern.get('avg_interval_ms', 0):.1f} ms")
    lines.append("")

    # Burst details
    bursts = pattern.get("bursts", [])
    if bursts:
        lines.append("### Burst Details")
        lines.append("")
        lines.append("| # | Start Time | Duration (ms) | Drop Count |")
        lines.append("|---|------------|---------------|------------|")
        for i, burst in enumerate(bursts, 1):
            lines.append(f"| {i} | {burst['start']} | {burst['duration_ms']:.1f} | {burst['count']} |")
        lines.append("")

    # Drop Timeline (if events exist)
    events = report.get("drop_events", [])
    if events:
        lines.append("## Drop Timeline")
        lines.append("")
        lines.append("| Time | Flow | Seq | Location | Description |")
        lines.append("|------|------|-----|----------|-------------|")
        for event in events[:20]:  # Limit to first 20
            time_str = event.get("timestamp", "")[:23]  # Trim to ms precision
            flow = f"{event.get('src_ip', '')} → {event.get('dst_ip', '')}"
            lines.append(f"| {time_str} | {flow} | {event.get('seq', '')} | {event.get('drop_type', '')} | {event.get('description', '')[:30]} |")
        if len(events) > 20:
            lines.append(f"| ... | *{len(events) - 20} more events* | | | |")
        lines.append("")

    # Recommendations
    recommendations = report.get("recommendations", [])
    lines.append("## Recommendations")
    lines.append("")
    if recommendations:
        for rec in recommendations:
            lines.append(f"- {rec}")
    else:
        lines.append("- No specific recommendations")
    lines.append("")

    return "\n".join(lines)


def analyze_drops(measurement_dir: Path) -> dict[str, Any]:
    """Main analysis function.

    Args:
        measurement_dir: Directory containing sender-host.log and receiver-host.log

    Returns:
        Complete analysis report dictionary
    """
    sender_log = measurement_dir / "sender-host.log"
    receiver_log = measurement_dir / "receiver-host.log"

    # Parse logs
    sender_content = sender_log.read_text() if sender_log.exists() else ""
    receiver_content = receiver_log.read_text() if receiver_log.exists() else ""

    sender_data = parse_log_file(sender_content, "tx") if sender_content else {"events": [], "stats": DropStats(0, 0, 0, 0, 0)}
    receiver_data = parse_log_file(receiver_content, "rx") if receiver_content else {"events": [], "stats": DropStats(0, 0, 0, 0, 0)}

    sender_stats = sender_data["stats"]
    receiver_stats = receiver_data["stats"]

    # Combine all events
    all_events = sender_data["events"] + receiver_data["events"]

    # Compute location attribution
    attribution = compute_location_attribution(sender_stats, receiver_stats)

    # Analyze patterns
    pattern_analysis = analyze_drop_patterns(all_events)

    # Generate recommendations
    recommendations = generate_recommendations(
        attribution, pattern_analysis, sender_stats, receiver_stats
    )

    # Build summary
    total_flows = sender_stats.total_flows + receiver_stats.total_flows
    complete_flows = sender_stats.complete_flows + receiver_stats.complete_flows
    total_drops = attribution["total_drops"]

    summary = {
        "total_drops": total_drops,
        "total_flows": total_flows,
        "complete_flows": complete_flows,
        "drop_rate_pct": round(total_drops / total_flows * 100, 2) if total_flows > 0 else 0,
    }

    # Convert events to serializable format
    events_serializable = [
        {
            "timestamp": e.timestamp.isoformat(),
            "src_ip": e.src_ip,
            "dst_ip": e.dst_ip,
            "icmp_id": e.icmp_id,
            "seq": e.seq,
            "drop_type": e.drop_type,
            "direction": e.direction,
            "description": e.description,
            "stages_seen": e.stages_seen,
        }
        for e in all_events
    ]

    return {
        "measurement_dir": str(measurement_dir),
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "drop_events": events_serializable,
        "location_attribution": attribution,
        "pattern_analysis": pattern_analysis,
        "recommendations": recommendations,
        "sender_stats": asdict(sender_stats) if hasattr(sender_stats, '__dataclass_fields__') else {
            "total_flows": sender_stats.total_flows,
            "complete_flows": sender_stats.complete_flows,
            "drop_0_1": sender_stats.drop_0_1,
            "drop_1_2": sender_stats.drop_1_2,
            "drop_2_3": sender_stats.drop_2_3,
        },
        "receiver_stats": asdict(receiver_stats) if hasattr(receiver_stats, '__dataclass_fields__') else {
            "total_flows": receiver_stats.total_flows,
            "complete_flows": receiver_stats.complete_flows,
            "drop_0_1": receiver_stats.drop_0_1,
            "drop_1_2": receiver_stats.drop_1_2,
            "drop_2_3": receiver_stats.drop_2_3,
        },
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_drops.py <measurement_dir>", file=sys.stderr)
        sys.exit(1)

    measurement_dir = Path(sys.argv[1])

    # Run analysis
    report = analyze_drops(measurement_dir)

    # Generate Markdown
    markdown = generate_markdown_report(report)

    # Save to file
    report_path = measurement_dir / "drop_report.md"
    report_path.write_text(markdown, encoding="utf-8")

    # Output JSON with report path and content
    output = {
        "report_path": str(report_path),
        "markdown_report": markdown,
        "detailed_report": report,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
