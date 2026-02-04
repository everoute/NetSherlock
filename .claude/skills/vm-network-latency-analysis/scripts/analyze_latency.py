#!/usr/bin/env python3
"""Analyze VM network latency from vm-network-path-tracer measurements.

Computes derived segments including physical network latency.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Import parser from vm-network-path-tracer
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "vm-network-path-tracer" / "scripts"))
from parse_icmp_verbose import parse_icmp_verbose_log


def parse_log_file(log_path: Path) -> dict[str, Any]:
    """Parse a single log file."""
    if not log_path.exists() or log_path.stat().st_size == 0:
        return {"error": f"Log file missing or empty: {log_path}", "flows": {"total": 0, "complete": 0}}

    content = log_path.read_text()
    return parse_icmp_verbose_log(content)


def compute_derived_segments(sender: dict, receiver: dict) -> dict[str, Any]:
    """Compute derived segments from sender and receiver data.

    Key derivation:
    - Physical Network = Sender.External - Receiver.Total
    - Receiver VM + Virt = Receiver.External
    - Unmeasured: Sender VM internal + Sender Virtualization
    """
    # Extract latency data
    sender_lat = sender.get("latency_us", {})
    receiver_lat = receiver.get("latency_us", {})

    # Get segment values (from segment1/segment2/segment3 structure)
    def get_seg(data: dict, seg_name: str) -> float:
        for key in ["segment1", "segment2", "segment3"]:
            if data.get(key, {}).get("name") == seg_name:
                return data[key].get("avg", 0)
        return 0

    s_req_internal = get_seg(sender_lat, "ReqInternal")
    s_external = get_seg(sender_lat, "External")
    s_rep_internal = get_seg(sender_lat, "RepInternal")
    s_total = sender_lat.get("total", {}).get("avg", 0)

    r_req_internal = get_seg(receiver_lat, "ReqInternal")
    r_external = get_seg(receiver_lat, "External")
    r_rep_internal = get_seg(receiver_lat, "RepInternal")
    r_total = receiver_lat.get("total", {}).get("avg", 0)

    # Derive physical network latency
    # Physical Network = S.External - R.Total
    physical_network = max(0, s_external - r_total)

    segments = {
        "S_ReqInternal": {
            "name": "Sender ReqInternal",
            "description": "Sender Host: vnet→phy (OVS forwarding, request)",
            "avg_us": s_req_internal,
            "source": "sender_host",
        },
        "S_RepInternal": {
            "name": "Sender RepInternal",
            "description": "Sender Host: phy→vnet (OVS forwarding, reply)",
            "avg_us": s_rep_internal,
            "source": "sender_host",
        },
        "Physical": {
            "name": "Physical Network",
            "description": "Wire latency (both directions)",
            "avg_us": physical_network,
            "source": "derived",
        },
        "R_ReqInternal": {
            "name": "Receiver ReqInternal",
            "description": "Receiver Host: phy→vnet (OVS forwarding, request)",
            "avg_us": r_req_internal,
            "source": "receiver_host",
        },
        "R_External": {
            "name": "Receiver External",
            "description": "Receiver: vnet→VM→vnet (VM + virtualization)",
            "avg_us": r_external,
            "source": "receiver_host",
        },
        "R_RepInternal": {
            "name": "Receiver RepInternal",
            "description": "Receiver Host: vnet→phy (OVS forwarding, reply)",
            "avg_us": r_rep_internal,
            "source": "receiver_host",
        },
    }

    return {
        "segments": segments,
        "sender_total": s_total,
        "receiver_total": r_total,
        "physical_network": physical_network,
    }


def compute_layer_attribution(segments: dict) -> list[dict]:
    """Compute layer-level latency attribution."""
    seg = segments["segments"]

    sender_ovs = seg["S_ReqInternal"]["avg_us"] + seg["S_RepInternal"]["avg_us"]
    physical = seg["Physical"]["avg_us"]
    receiver_ovs = seg["R_ReqInternal"]["avg_us"] + seg["R_RepInternal"]["avg_us"]
    receiver_vm = seg["R_External"]["avg_us"]

    total = sender_ovs + physical + receiver_ovs + receiver_vm

    layers = [
        {
            "name": "Sender Host OVS",
            "segments": ["S_ReqInternal", "S_RepInternal"],
            "total_us": sender_ovs,
            "percentage": (sender_ovs / total * 100) if total > 0 else 0,
        },
        {
            "name": "Physical Network",
            "segments": ["Physical"],
            "total_us": physical,
            "percentage": (physical / total * 100) if total > 0 else 0,
        },
        {
            "name": "Receiver Host OVS",
            "segments": ["R_ReqInternal", "R_RepInternal"],
            "total_us": receiver_ovs,
            "percentage": (receiver_ovs / total * 100) if total > 0 else 0,
        },
        {
            "name": "Receiver VM + Virtualization",
            "segments": ["R_External"],
            "total_us": receiver_vm,
            "percentage": (receiver_vm / total * 100) if total > 0 else 0,
        },
    ]

    # Sort by contribution (highest first)
    layers.sort(key=lambda x: x["total_us"], reverse=True)
    return layers


def generate_data_path_diagram(report: dict) -> str:
    """Generate ASCII data path diagram."""
    seg = report.get("segments", {})

    def fmt(s: str) -> str:
        val = seg.get(s, {}).get("avg_us", 0)
        return f"{val:.1f}us"

    diagram = f"""
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal: {fmt('S_ReqInternal'):>8}]      [Physical: {fmt('Physical'):>8}]      [R.ReqInternal: {fmt('R_ReqInternal'):>8}]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                       {fmt('R_External'):>8}
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal: {fmt('S_RepInternal'):>8}]                                [R.RepInternal: {fmt('R_RepInternal'):>8}]

Sender Total: {report.get('sender_total', 0):.1f}us | Receiver Total: {report.get('receiver_total', 0):.1f}us
Physical Network (derived) = Sender.External - Receiver.Total = {fmt('Physical')}
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
"""
    return diagram.strip()


def generate_markdown_report(report: dict) -> str:
    """Generate Markdown report."""
    lines = []

    # Header
    lines.append("# VM Network Latency Analysis Report")
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
    lines.append(f"| **Sender Total RTT** | {summary.get('sender_total_us', 0):.2f} us |")
    lines.append(f"| **Receiver Total RTT** | {summary.get('receiver_total_us', 0):.2f} us |")
    lines.append(f"| **Physical Network (derived)** | {summary.get('physical_network_us', 0):.2f} us |")
    lines.append(f"| **Primary Contributor** | {summary.get('primary_contributor', 'Unknown')} |")
    lines.append(f"| **Sample Count** | {summary.get('sample_count', 0)} |")
    lines.append("")

    # Layer Attribution
    layers = report.get("layer_attribution_sorted", [])
    if layers:
        lines.append("## Layer Attribution")
        lines.append("")
        lines.append("| Layer | Latency (us) | Percentage | Segments |")
        lines.append("|-------|-------------|------------|----------|")
        for layer in layers:
            name = layer.get("name", "Unknown")
            latency = layer.get("total_us", 0)
            pct = layer.get("percentage", 0)
            segments = ", ".join(layer.get("segments", []))
            lines.append(f"| {name} | {latency:.2f} | {pct:.1f}% | {segments} |")
        lines.append("")
        lines.append("*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*")
        lines.append("")

    # Segment Breakdown
    segments = report.get("segments", {})
    if segments:
        lines.append("## Segment Breakdown")
        lines.append("")
        lines.append("| Segment | Latency (us) | Source | Description |")
        lines.append("|---------|-------------|--------|-------------|")
        for seg_id in ["S_ReqInternal", "Physical", "R_ReqInternal", "R_External", "R_RepInternal", "S_RepInternal"]:
            seg = segments.get(seg_id, {})
            name = seg.get("name", seg_id)
            avg = seg.get("avg_us", 0)
            source = seg.get("source", "")
            desc = seg.get("description", "")[:40]
            lines.append(f"| {name} | {avg:.2f} | {source} | {desc} |")
        lines.append("")

    # Data Path Diagram
    diagram = generate_data_path_diagram(report)
    lines.append("## Data Path Diagram")
    lines.append("")
    lines.append("```")
    lines.append(diagram)
    lines.append("```")
    lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    lines.append("")
    primary = layers[0] if layers else {}
    lines.append(f"- **Primary Bottleneck**: {primary.get('name', 'Unknown')} ({primary.get('total_us', 0):.1f}us, {primary.get('percentage', 0):.1f}%)")

    physical_us = report.get("segments", {}).get("Physical", {}).get("avg_us", 0)
    if physical_us > 100:
        lines.append(f"- **Physical Network**: {physical_us:.1f}us - check switch/cable quality")
    else:
        lines.append(f"- **Physical Network**: {physical_us:.1f}us - within normal range")

    lines.append("- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)")
    lines.append("")

    return "\n".join(lines)


def analyze_latency(measurement_dir: Path) -> dict[str, Any]:
    """Main analysis function."""
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

    summary = {
        "sender_total_us": derived["sender_total"],
        "receiver_total_us": derived["receiver_total"],
        "physical_network_us": derived["physical_network"],
        "primary_contributor": primary.get("name", "Unknown"),
        "primary_contributor_pct": primary.get("percentage", 0),
        "sample_count": sender.get("flows", {}).get("complete", 0),
    }

    return {
        "measurement_dir": str(measurement_dir),
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "segments": derived["segments"],
        "layer_attribution_sorted": layers,
        "sender_total": derived["sender_total"],
        "receiver_total": derived["receiver_total"],
        "raw_data": {
            "sender": sender,
            "receiver": receiver,
        },
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: analyze_latency.py <measurement_dir>", file=sys.stderr)
        sys.exit(1)

    measurement_dir = Path(sys.argv[1])
    report = analyze_latency(measurement_dir)

    # Generate Markdown
    markdown = generate_markdown_report(report)

    # Save to file
    report_path = measurement_dir / "vm_latency_report.md"
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
