#!/usr/bin/env python3
"""Analyze VM network packet drops from vm-network-path-tracer measurements.

Parses dual-host logs, extracts drop events, computes location attribution,
and generates diagnostic reports.
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Import parser from vm-network-path-tracer
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "vm-network-path-tracer" / "scripts"))
from parse_icmp_verbose import parse_icmp_verbose_log


@dataclass
class DropEvent:
    """A single drop event."""

    timestamp_ns: int
    flow_id: int
    drop_type: str  # drop_0_1, drop_1_2, drop_2_3
    host: str  # sender or receiver
    description: str
    last_seen_point: str
    expected_point: str


@dataclass
class DropStats:
    """Aggregated drop statistics."""

    total_drops: int = 0
    total_flows: int = 0
    complete_flows: int = 0
    drop_0_1: int = 0  # req_internal
    drop_1_2: int = 0  # external (receiver only)
    drop_2_3: int = 0  # rep_internal
    events: list = field(default_factory=list)


def parse_log_file(log_path: Path) -> dict[str, Any]:
    """Parse a single log file."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return {"error": f"Log file missing or empty: {log_path}", "flows": {"total": 0, "complete": 0}}

    content = log_path.read_text()
    return parse_icmp_verbose_log(content)


def extract_drops(parsed: dict, host: str) -> DropStats:
    """Extract drop events from parsed log data."""
    stats = DropStats()

    flows = parsed.get("flows", {})
    stats.total_flows = flows.get("total", 0)
    stats.complete_flows = flows.get("complete", 0)

    # Count drops by type
    drop_counts = parsed.get("drop_counts", {})
    stats.drop_0_1 = drop_counts.get("drop_0_1", 0)
    stats.drop_1_2 = drop_counts.get("drop_1_2", 0)
    stats.drop_2_3 = drop_counts.get("drop_2_3", 0)
    stats.total_drops = stats.drop_0_1 + stats.drop_1_2 + stats.drop_2_3

    # Extract individual drop events
    incomplete = parsed.get("incomplete_flows", [])
    for flow in incomplete:
        flow_id = flow.get("flow_id", 0)
        points = flow.get("points", [])
        drop_type = flow.get("drop_type", "unknown")

        # Determine last seen and expected points
        last_seen = points[-1] if points else "none"
        expected = _get_expected_point(drop_type, host)

        event = DropEvent(
            timestamp_ns=flow.get("timestamps", [0])[-1] if flow.get("timestamps") else 0,
            flow_id=flow_id,
            drop_type=drop_type,
            host=host,
            description=_get_drop_description(drop_type, host),
            last_seen_point=last_seen,
            expected_point=expected,
        )
        stats.events.append(event)

    return stats


def _get_expected_point(drop_type: str, host: str) -> str:
    """Get the expected point name for a drop type."""
    mapping = {
        "drop_0_1": "point1 (after OVS forwarding)",
        "drop_1_2": "point2 (reply from VM)",
        "drop_2_3": "point3 (phy TX)",
    }
    return mapping.get(drop_type, "unknown")


def _get_drop_description(drop_type: str, host: str) -> str:
    """Get human-readable description for drop type."""
    if host == "sender":
        descriptions = {
            "drop_0_1": "Request dropped in Sender vnet→phy path (OVS)",
            "drop_1_2": "External drop (unexpected for sender)",
            "drop_2_3": "Reply dropped in Sender phy→vnet path (OVS)",
        }
    else:  # receiver
        descriptions = {
            "drop_0_1": "Request dropped in Receiver phy→vnet path (OVS)",
            "drop_1_2": "VM did not respond (ping timeout or VM issue)",
            "drop_2_3": "Reply dropped in Receiver vnet→phy path (OVS)",
        }
    return descriptions.get(drop_type, f"Unknown drop type: {drop_type}")


def compute_location_attribution(sender_stats: DropStats, receiver_stats: DropStats) -> dict[str, Any]:
    """Compute drop location attribution."""
    attribution = {
        "sender_host_ovs": sender_stats.drop_0_1 + sender_stats.drop_2_3,
        "receiver_host_ovs": receiver_stats.drop_0_1 + receiver_stats.drop_2_3,
        "receiver_vm": receiver_stats.drop_1_2,
        "physical_network": 0,  # Inferred from cross-host correlation
    }

    # Simple inference: if sender sees external drop but receiver sees complete flow,
    # it might be physical network. This is simplified - real correlation is complex.
    total = sum(attribution.values())

    return {
        "by_location": attribution,
        "total_attributed": total,
        "primary_location": max(attribution, key=attribution.get) if total > 0 else "none",
    }


def analyze_drop_pattern(events: list[DropEvent]) -> dict[str, Any]:
    """Analyze drop patterns (burst vs sporadic)."""
    if not events:
        return {"pattern_type": "none", "burst_events": 0, "sporadic_events": 0, "avg_interval_ms": 0}

    # Sort by timestamp
    sorted_events = sorted(events, key=lambda e: e.timestamp_ns)

    # Calculate intervals
    intervals = []
    for i in range(1, len(sorted_events)):
        interval_ns = sorted_events[i].timestamp_ns - sorted_events[i - 1].timestamp_ns
        intervals.append(interval_ns / 1_000_000)  # Convert to ms

    if not intervals:
        return {"pattern_type": "single", "burst_events": 0, "sporadic_events": 1, "avg_interval_ms": 0}

    avg_interval = sum(intervals) / len(intervals)

    # Classify: burst if intervals < 100ms, sporadic otherwise
    burst_threshold_ms = 100
    burst_count = sum(1 for i in intervals if i < burst_threshold_ms)
    sporadic_count = len(intervals) - burst_count

    if burst_count > sporadic_count:
        pattern = "burst"
    elif sporadic_count > burst_count:
        pattern = "sporadic"
    else:
        pattern = "mixed"

    return {
        "pattern_type": pattern,
        "burst_events": burst_count,
        "sporadic_events": sporadic_count,
        "avg_interval_ms": avg_interval,
    }


def generate_recommendations(attribution: dict, pattern: dict, sender: DropStats, receiver: DropStats) -> list[str]:
    """Generate diagnostic recommendations."""
    recommendations = []
    total_drops = sender.total_drops + receiver.total_drops

    if total_drops == 0:
        recommendations.append("No drops detected - VM network path is stable")
        return recommendations

    loc = attribution.get("by_location", {})

    # Location-based recommendations
    if loc.get("sender_host_ovs", 0) > 0:
        recommendations.append(
            f"Sender Host OVS drops ({loc['sender_host_ovs']}): "
            "Check OVS flow rules, bridge configuration, and vnet interface status"
        )

    if loc.get("receiver_host_ovs", 0) > 0:
        recommendations.append(
            f"Receiver Host OVS drops ({loc['receiver_host_ovs']}): "
            "Check OVS flow rules, bridge configuration, and vnet interface status"
        )

    if loc.get("receiver_vm", 0) > 0:
        recommendations.append(
            f"Receiver VM drops ({loc['receiver_vm']}): "
            "Check VM network stack, firewall rules, and ICMP response settings"
        )

    # Pattern-based recommendations
    if pattern.get("pattern_type") == "burst":
        recommendations.append(
            "Burst pattern detected: May indicate queue overflow, rate limiting, or transient congestion"
        )
    elif pattern.get("pattern_type") == "sporadic":
        recommendations.append("Sporadic pattern detected: May indicate intermittent issues or packet filtering")

    return recommendations


def generate_markdown_report(report: dict) -> str:
    """Generate Markdown report."""
    lines = []

    # Header
    lines.append("# VM Network Drop Analysis Report")
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
    lines.append(f"| **Drop Rate** | {summary.get('drop_rate', 0):.2f}% |")
    lines.append(f"| **Total Flows** | {summary.get('total_flows', 0)} |")
    lines.append(f"| **Complete Flows** | {summary.get('complete_flows', 0)} |")
    lines.append("")

    # Location Attribution
    attribution = report.get("attribution", {}).get("by_location", {})
    if any(attribution.values()):
        lines.append("## Drop Location Attribution")
        lines.append("")
        lines.append("| Location | Drops | Description |")
        lines.append("|----------|-------|-------------|")
        lines.append(
            f"| Sender Host OVS | {attribution.get('sender_host_ovs', 0)} | vnet↔phy forwarding issues |"
        )
        lines.append(
            f"| Receiver Host OVS | {attribution.get('receiver_host_ovs', 0)} | phy↔vnet forwarding issues |"
        )
        lines.append(f"| Receiver VM | {attribution.get('receiver_vm', 0)} | VM not responding |")
        lines.append("")

    # Drop Breakdown by Host
    sender = report.get("sender_stats", {})
    receiver = report.get("receiver_stats", {})

    lines.append("## Drop Breakdown by Type")
    lines.append("")
    lines.append("### Sender Host")
    lines.append("")
    lines.append("| Drop Type | Count | Description |")
    lines.append("|-----------|-------|-------------|")
    lines.append(f"| drop_0_1 | {sender.get('drop_0_1', 0)} | vnet→phy (request path) |")
    lines.append(f"| drop_2_3 | {sender.get('drop_2_3', 0)} | phy→vnet (reply path) |")
    lines.append("")

    lines.append("### Receiver Host")
    lines.append("")
    lines.append("| Drop Type | Count | Description |")
    lines.append("|-----------|-------|-------------|")
    lines.append(f"| drop_0_1 | {receiver.get('drop_0_1', 0)} | phy→vnet (request path) |")
    lines.append(f"| drop_1_2 | {receiver.get('drop_1_2', 0)} | VM no reply |")
    lines.append(f"| drop_2_3 | {receiver.get('drop_2_3', 0)} | vnet→phy (reply path) |")
    lines.append("")

    # Pattern Analysis
    pattern = report.get("pattern", {})
    lines.append("## Pattern Analysis")
    lines.append("")
    lines.append(f"- **Pattern Type**: {pattern.get('pattern_type', 'unknown')}")
    lines.append(f"- **Burst Events**: {pattern.get('burst_events', 0)}")
    lines.append(f"- **Sporadic Events**: {pattern.get('sporadic_events', 0)}")
    lines.append(f"- **Average Interval**: {pattern.get('avg_interval_ms', 0):.1f} ms")
    lines.append("")

    # Recommendations
    recommendations = report.get("recommendations", [])
    lines.append("## Recommendations")
    lines.append("")
    for rec in recommendations:
        lines.append(f"- {rec}")
    lines.append("")

    return "\n".join(lines)


def analyze_drops(measurement_dir: Path) -> dict[str, Any]:
    """Main analysis function."""
    sender_log = measurement_dir / "sender-host.log"
    receiver_log = measurement_dir / "receiver-host.log"

    sender_parsed = parse_log_file(sender_log)
    receiver_parsed = parse_log_file(receiver_log)

    sender_stats = extract_drops(sender_parsed, "sender")
    receiver_stats = extract_drops(receiver_parsed, "receiver")

    # Combine all events for pattern analysis
    all_events = sender_stats.events + receiver_stats.events

    # Compute attribution and pattern
    attribution = compute_location_attribution(sender_stats, receiver_stats)
    pattern = analyze_drop_pattern(all_events)

    # Generate recommendations
    recommendations = generate_recommendations(attribution, pattern, sender_stats, receiver_stats)

    # Build summary
    total_flows = max(sender_stats.total_flows, receiver_stats.total_flows)
    total_drops = sender_stats.total_drops + receiver_stats.total_drops
    drop_rate = (total_drops / total_flows * 100) if total_flows > 0 else 0

    summary = {
        "total_drops": total_drops,
        "drop_rate": drop_rate,
        "total_flows": total_flows,
        "complete_flows": min(sender_stats.complete_flows, receiver_stats.complete_flows),
    }

    return {
        "measurement_dir": str(measurement_dir),
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "attribution": attribution,
        "pattern": pattern,
        "recommendations": recommendations,
        "sender_stats": {
            "total_drops": sender_stats.total_drops,
            "drop_0_1": sender_stats.drop_0_1,
            "drop_1_2": sender_stats.drop_1_2,
            "drop_2_3": sender_stats.drop_2_3,
        },
        "receiver_stats": {
            "total_drops": receiver_stats.total_drops,
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
    report = analyze_drops(measurement_dir)

    # Generate Markdown
    markdown = generate_markdown_report(report)

    # Save to file
    report_path = measurement_dir / "vm_drop_report.md"
    report_path.write_text(markdown, encoding="utf-8")

    # Output JSON
    output = {
        "report_path": str(report_path),
        "markdown_report": markdown,
        "detailed_report": report,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
