#!/usr/bin/env python3
"""Generate Markdown diagnosis report from measurement data."""

import json
import sys
from pathlib import Path

# Import the analysis module
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from analyze_measurement import analyze_measurements


def generate_markdown_report(report: dict) -> str:
    """Generate Markdown report from analysis data."""
    lines = []

    # Header
    lines.append("# VM Cross-Node ICMP Latency Diagnosis Report")
    lines.append("")
    lines.append(f"**Measurement Directory**: `{report.get('measurement_dir', 'N/A')}`")
    lines.append(f"**Analysis Time**: {report.get('timestamp', 'N/A')}")
    lines.append("")

    # Summary
    summary = report.get("summary", {})
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Total RTT** | {summary.get('total_rtt_us', 0):.2f} µs ({summary.get('total_rtt_ms', 0):.3f} ms) |")
    lines.append(f"| **Primary Contributor** | {summary.get('primary_contributor_name', 'Unknown')} |")
    lines.append(f"| **Contribution** | {summary.get('primary_contributor_pct', 0):.1f}% |")
    lines.append(f"| **Sample Count** | {summary.get('sample_count', 0)} |")
    lines.append(f"| **Validation Error** | {summary.get('validation_error_pct', 0):.2f}% |")
    lines.append("")

    # Layer Attribution
    layer_sorted = report.get("layer_attribution_sorted", [])
    if layer_sorted:
        lines.append("## Layer Attribution")
        lines.append("")
        lines.append("| Layer | Latency (µs) | Percentage | Segments |")
        lines.append("|-------|-------------|------------|----------|")
        for layer in layer_sorted:
            name = layer.get("name", layer.get("layer", "Unknown"))
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
        lines.append("| Segment | Description | Avg (µs) | StdDev | Min | Max | Samples |")
        lines.append("|---------|-------------|----------|--------|-----|-----|---------|")
        for seg_name, seg_data in segments.items():
            desc = seg_data.get("description", "")[:30]
            avg = seg_data.get("avg_us", 0)
            stddev = seg_data.get("stddev_us", 0)
            min_v = seg_data.get("min_us", 0)
            max_v = seg_data.get("max_us", 0)
            samples = seg_data.get("samples", 0)
            lines.append(f"| {seg_name} | {desc} | {avg:.2f} | {stddev:.2f} | {min_v:.2f} | {max_v:.2f} | {samples} |")
        lines.append("")

    # Data Path Diagram
    diagram = report.get("data_path_diagram", "")
    if diagram:
        lines.append("## Data Path Diagram")
        lines.append("")
        lines.append("```")
        lines.append(diagram)
        lines.append("```")
        lines.append("")

    # Key Findings
    findings = report.get("findings", [])
    if findings:
        lines.append("## Key Findings")
        lines.append("")
        for finding in findings:
            f_type = finding.get("type", "unknown")
            title = finding.get("title", f_type)
            lines.append(f"### {title}")
            lines.append("")

            if f_type == "total_latency":
                lines.append(f"- **Value**: {finding.get('value_us', 0):.2f} µs")
                lines.append(f"- **Range**: {finding.get('min_us', 0):.2f} - {finding.get('max_us', 0):.2f} µs")
                lines.append(f"- **StdDev**: {finding.get('stddev_us', 0):.2f} µs")
            elif f_type == "primary_bottleneck":
                lines.append(f"- **Layer**: {finding.get('layer_name', 'Unknown')}")
                lines.append(f"- **Latency**: {finding.get('latency_us', 0):.2f} µs ({finding.get('percentage', 0):.1f}%)")
                lines.append(f"- **Segments**: {', '.join(finding.get('segments', []))}")
            elif f_type == "variance_analysis":
                lines.append("High variance segments:")
                lines.append("")
                for seg in finding.get("segments", []):
                    lines.append(f"- **{seg.get('name')}**: CV={seg.get('cv_pct', 0):.1f}%, Avg={seg.get('avg_us', 0):.2f}µs, StdDev={seg.get('stddev_us', 0):.2f}µs")
            elif f_type == "top_contributors":
                for layer in finding.get("layers", []):
                    lines.append(f"- **{layer.get('layer_name')}**: {layer.get('latency_us', 0):.2f}µs ({layer.get('percentage', 0):.1f}%)")
            lines.append("")

    # Validation
    validation = report.get("validation", {})
    if validation:
        lines.append("## Validation")
        lines.append("")
        lines.append(f"| Check | Value |")
        lines.append(f"|-------|-------|")
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
