#!/usr/bin/env python3
"""Generate Markdown diagnosis report from system network measurement data."""

import json
import sys
from pathlib import Path

# Import the analysis module
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from analyze_measurement import analyze_measurements


def generate_data_path_diagram(report: dict) -> str:
    """Generate ASCII data path diagram with measured values."""
    seg = report.get("segments", {})

    def fmt(s: str) -> str:
        val = seg.get(s, {}).get("avg_us", 0)
        return f"{val:.1f}µs"

    diagram = f"""
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │  {fmt('A'):>10}          │      │  {fmt('C'):>10}    │      │   │  {fmt('D'):>10}          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │  {fmt('E'):>10}          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │  {fmt('F'):>10}          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │  {fmt('J'):>10}    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │  {fmt('G'):>10}          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = {report.get('summary', {}).get('total_rtt_us', 0):.1f} µs
"""
    return diagram.strip()


def generate_markdown_report(report: dict) -> str:
    """Generate Markdown report from analysis data."""
    lines = []

    # Header
    lines.append("# System Network Latency Diagnosis Report")
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
    lines.append(f"| **Total RTT** | {summary.get('total_rtt_us', 0):.2f} µs ({summary.get('total_rtt_ms', 0):.3f} ms) |")
    lines.append(f"| **Primary Contributor** | {summary.get('primary_contributor', 'Unknown')} |")
    lines.append(f"| **Contribution** | {summary.get('primary_contributor_pct', 0):.1f}% |")
    lines.append(f"| **Sample Count** | {summary.get('sample_count', 0)} |")
    lines.append("")

    # Layer Attribution
    layers = report.get("layer_attribution_sorted", [])
    if layers:
        lines.append("## Layer Attribution")
        lines.append("")
        lines.append("| Layer | Latency (µs) | Percentage | Segments |")
        lines.append("|-------|-------------|------------|----------|")
        for layer in layers:
            name = layer.get("name", "Unknown")
            latency = layer.get("total_us", 0)
            pct = layer.get("percentage", 0)
            segments = ", ".join(layer.get("segments", []))
            lines.append(f"| {name} | {latency:.2f} | {pct:.1f}% | {segments} |")
        lines.append("")

    # Segment Breakdown
    segments = report.get("segments", {})
    if segments:
        lines.append("## Segment Breakdown")
        lines.append("")
        lines.append("| Segment | Name | Latency (µs) | Source | Description |")
        lines.append("|---------|------|-------------|--------|-------------|")
        for seg_id in ["A", "C", "D", "E", "F", "J", "G"]:
            seg = segments.get(seg_id, {})
            name = seg.get("name", "")
            avg = seg.get("avg_us", 0)
            source = seg.get("source", "")
            desc = seg.get("description", "")[:40]
            lines.append(f"| {seg_id} | {name} | {avg:.2f} | {source} | {desc} |")
        lines.append("")

    # Data Path Diagram
    diagram = generate_data_path_diagram(report)
    lines.append("## Data Path Diagram")
    lines.append("")
    lines.append("```")
    lines.append(diagram)
    lines.append("```")
    lines.append("")

    # Drop Statistics
    drops = report.get("drops", {})
    sender_drops = drops.get("sender", {})
    receiver_drops = drops.get("receiver", {})
    has_drops = any(v > 0 for v in sender_drops.values()) or any(v > 0 for v in receiver_drops.values())

    lines.append("## Drop Statistics")
    lines.append("")
    if has_drops:
        lines.append("| Location | Type | Count |")
        lines.append("|----------|------|-------|")
        for drop_type, count in sender_drops.items():
            if count > 0:
                lines.append(f"| Sender | {drop_type} | **{count}** |")
        for drop_type, count in receiver_drops.items():
            if count > 0:
                lines.append(f"| Receiver | {drop_type} | **{count}** |")
    else:
        lines.append("✅ No packet drops detected during measurement period.")
    lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    lines.append("")

    # Primary bottleneck
    primary = layers[0] if layers else {}
    lines.append("### Primary Latency Contributor")
    lines.append("")
    lines.append(f"- **Layer**: {primary.get('name', 'Unknown')}")
    lines.append(f"- **Latency**: {primary.get('total_us', 0):.2f} µs ({primary.get('percentage', 0):.1f}%)")
    lines.append(f"- **Segments**: {', '.join(primary.get('segments', []))}")
    lines.append("")

    # Latency assessment
    total = summary.get("total_rtt_us", 0)
    if total > 1000:
        lines.append("### ⚠️ High Latency")
        lines.append(f"Total RTT ({total:.1f} µs) exceeds 1ms threshold.")
    elif total > 500:
        lines.append("### ℹ️ Moderate Latency")
        lines.append(f"Total RTT: {total:.1f} µs")
    else:
        lines.append("### ✅ Low Latency")
        lines.append(f"Total RTT: {total:.1f} µs (excellent)")
    lines.append("")

    # Validation
    validation = report.get("validation", {})
    if validation:
        lines.append("## Validation")
        lines.append("")
        lines.append("| Check | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Measured Total | {validation.get('measured_total_us', 0):.2f} µs |")
        lines.append(f"| Calculated Total | {validation.get('calculated_total_us', 0):.2f} µs |")
        lines.append(f"| Difference | {validation.get('difference_us', 0):.2f} µs ({validation.get('error_pct', 0):.2f}%) |")
        lines.append(f"| Status | **{validation.get('status', 'Unknown')}** |")
        lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: generate_report.py <measurement_dir>", file=sys.stderr)
        sys.exit(1)

    measurement_dir = Path(sys.argv[1])

    # Run analysis
    report = analyze_measurements(measurement_dir)

    # Generate Markdown
    markdown = generate_markdown_report(report)

    # Save to file
    report_path = measurement_dir / "diagnosis_report.md"
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
