#!/usr/bin/env python3
"""Analyze system network measurement logs and compute segment latencies."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent path for parse_icmp_verbose import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "system-network-path-tracer" / "scripts"))
from parse_icmp_verbose import parse_icmp_verbose_log


def detect_direction(content: str) -> str:
    """Detect TX or RX direction from log content."""
    if "Direction: TX" in content:
        return "tx"
    return "rx"


def parse_log_file(log_path: Path) -> dict[str, Any]:
    """Parse a single log file with auto-detected direction."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return {"error": f"Log file missing or empty: {log_path}", "flows": {"total": 0, "complete": 0}}

    content = log_path.read_text()
    direction = detect_direction(content)
    return parse_icmp_verbose_log(content, direction)


def get_segment_by_name(latency_data: dict, name: str) -> dict:
    """Get segment data by name from latency_us structure.

    The parse_icmp_verbose_log returns segments as segment1, segment2, etc.
    with a 'name' field inside. This helper finds the segment by its name.
    """
    name_lower = name.lower()
    for key, value in latency_data.items():
        if isinstance(value, dict) and value.get("name", "").lower() == name_lower:
            return value
    return {}


def compute_derived_segments(sender: dict, receiver: dict) -> dict[str, Any]:
    """Compute derived segments from sender TX and receiver RX data.

    Returns segment breakdown with:
    - A: Sender ReqPath (ip_send_skb → phy TX)
    - C: Wire request (derived)
    - D: Receiver ReqPath (phy RX → icmp_rcv)
    - E: Receiver Stack (icmp_rcv → ip_send_skb)
    - F: Receiver RepPath (ip_send_skb → phy TX)
    - J: Wire reply (derived)
    - G: Sender RepPath (phy RX → ping_rcv)
    """
    # Extract latency data
    sender_lat = sender.get("latency_us", {})
    receiver_lat = receiver.get("latency_us", {})

    # Sender TX mode segments (by name)
    sender_req_path = get_segment_by_name(sender_lat, "ReqPath").get("avg", 0)
    sender_external = get_segment_by_name(sender_lat, "External").get("avg", 0)
    sender_rep_path = get_segment_by_name(sender_lat, "RepPath").get("avg", 0)
    sender_total = sender_lat.get("total", {}).get("avg", 0)

    # Receiver RX mode segments (by name)
    receiver_req_path = get_segment_by_name(receiver_lat, "ReqPath").get("avg", 0)
    receiver_stack = get_segment_by_name(receiver_lat, "Stack").get("avg", 0)
    receiver_rep_path = get_segment_by_name(receiver_lat, "RepPath").get("avg", 0)
    receiver_total = receiver_lat.get("total", {}).get("avg", 0)

    # Derive wire latency
    # Wire(C) + Wire(J) = Sender.External - Receiver.Total
    wire_total = max(0, sender_external - receiver_total)
    wire_one_way = wire_total / 2  # Assume symmetric

    segments = {
        "A": {
            "name": "Sender ReqPath",
            "description": "Sender kernel TX processing (ip_send_skb → phy TX)",
            "avg_us": sender_req_path,
            "source": "sender_tx",
        },
        "C": {
            "name": "Wire (Request)",
            "description": "Physical network transit (request direction)",
            "avg_us": wire_one_way,
            "source": "derived",
        },
        "D": {
            "name": "Receiver ReqPath",
            "description": "Receiver kernel RX processing (phy RX → icmp_rcv)",
            "avg_us": receiver_req_path,
            "source": "receiver_rx",
        },
        "E": {
            "name": "Receiver Stack",
            "description": "Receiver ICMP echo processing (icmp_rcv → ip_send_skb)",
            "avg_us": receiver_stack,
            "source": "receiver_rx",
        },
        "F": {
            "name": "Receiver RepPath",
            "description": "Receiver kernel TX processing (ip_send_skb → phy TX)",
            "avg_us": receiver_rep_path,
            "source": "receiver_rx",
        },
        "J": {
            "name": "Wire (Reply)",
            "description": "Physical network transit (reply direction)",
            "avg_us": wire_one_way,
            "source": "derived",
        },
        "G": {
            "name": "Sender RepPath",
            "description": "Sender kernel RX processing (phy RX → ping_rcv)",
            "avg_us": sender_rep_path,
            "source": "sender_tx",
        },
    }

    return {
        "segments": segments,
        "sender_total": sender_total,
        "receiver_total": receiver_total,
        "wire_total": wire_total,
    }


def compute_layer_attribution(segments: dict) -> list[dict]:
    """Compute layer-level latency attribution."""
    seg = segments["segments"]

    sender_internal = seg["A"]["avg_us"] + seg["G"]["avg_us"]
    receiver_internal = seg["D"]["avg_us"] + seg["E"]["avg_us"] + seg["F"]["avg_us"]
    network = seg["C"]["avg_us"] + seg["J"]["avg_us"]

    total = sender_internal + receiver_internal + network

    layers = [
        {
            "name": "Sender Host Internal",
            "segments": ["A", "G"],
            "total_us": sender_internal,
            "percentage": (sender_internal / total * 100) if total > 0 else 0,
        },
        {
            "name": "Receiver Host Internal",
            "segments": ["D", "E", "F"],
            "total_us": receiver_internal,
            "percentage": (receiver_internal / total * 100) if total > 0 else 0,
        },
        {
            "name": "Physical Network",
            "segments": ["C", "J"],
            "total_us": network,
            "percentage": (network / total * 100) if total > 0 else 0,
        },
    ]

    # Sort by contribution (highest first)
    layers.sort(key=lambda x: x["total_us"], reverse=True)
    return layers


def analyze_measurements(measurement_dir: Path) -> dict[str, Any]:
    """Main analysis function.

    Args:
        measurement_dir: Directory containing sender-host.log and receiver-host.log

    Returns:
        Complete analysis report dictionary
    """
    sender_log = measurement_dir / "sender-host.log"
    receiver_log = measurement_dir / "receiver-host.log"

    sender = parse_log_file(sender_log)
    receiver = parse_log_file(receiver_log)

    # Compute derived segments
    derived = compute_derived_segments(sender, receiver)

    # Compute layer attribution
    layers = compute_layer_attribution(derived)

    # Build summary
    primary = layers[0] if layers else {}
    total_rtt = derived["sender_total"]

    summary = {
        "total_rtt_us": total_rtt,
        "total_rtt_ms": total_rtt / 1000,
        "primary_contributor": primary.get("name", "Unknown"),
        "primary_contributor_pct": primary.get("percentage", 0),
        "sample_count": sender.get("flows", {}).get("complete", 0),
    }

    # Validation
    calculated = sum(s["avg_us"] for s in derived["segments"].values())
    diff = abs(total_rtt - calculated)
    validation = {
        "measured_total_us": total_rtt,
        "calculated_total_us": calculated,
        "difference_us": diff,
        "error_pct": (diff / total_rtt * 100) if total_rtt > 0 else 0,
        "status": "Valid" if diff < total_rtt * 0.1 else "Warning",
    }

    # Drop statistics
    drops = {
        "sender": sender.get("drops", {}),
        "receiver": receiver.get("drops", {}),
    }

    return {
        "measurement_dir": str(measurement_dir),
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "segments": derived["segments"],
        "layer_attribution_sorted": layers,
        "validation": validation,
        "drops": drops,
        "raw_data": {
            "sender": sender,
            "receiver": receiver,
        },
    }
