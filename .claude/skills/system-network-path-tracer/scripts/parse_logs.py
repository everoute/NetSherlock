#!/usr/bin/env python3
"""Parse system network path tracer log files (v2).

Routes to protocol-specific parsers based on log content detection.
Outputs readable Markdown reports (or JSON with --json flag).

Focus modes:
- drop: Emphasize drop statistics, latency only shows total
- latency: Full latency segment analysis with data path diagram and percentages

Supported formats:
- ICMP verbose: system_icmp_path_tracer.py with --verbose
- TCP/UDP verbose: system_tcp_path_tracer.py / system_udp_path_tracer.py --verbose (reserved)
- TCP/UDP stats: system_tcp_path_tracer.py / system_udp_path_tracer.py --stats-interval (reserved)
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional, Tuple


def detect_log_format(content: str) -> Tuple[str, str, str]:
    """Detect protocol, output mode, and direction from log content.

    Returns: (protocol, output_mode, direction)
    """
    # Detect protocol
    if 'System ICMP Path Tracer' in content:
        protocol = 'icmp'
        output_mode = 'verbose'  # ICMP only has verbose mode
        # Detect direction
        if 'Direction: TX' in content:
            direction = 'tx'
        else:
            direction = 'rx'
        return (protocol, output_mode, direction)

    elif 'System TCP Path Tracer' in content:
        protocol = 'tcp'
        if 'Mode: Stats' in content:
            output_mode = 'stats'
        else:
            output_mode = 'verbose'
        return (protocol, output_mode, 'bidirectional')

    elif 'System UDP Path Tracer' in content:
        protocol = 'udp'
        if 'Mode: Stats' in content:
            output_mode = 'stats'
        else:
            output_mode = 'verbose'
        return (protocol, output_mode, 'bidirectional')

    return ('unknown', 'unknown', 'unknown')


def parse_log_file(log_path: str, protocol: Optional[str] = None,
                   direction: Optional[str] = None) -> dict:
    """Parse a single log file using the appropriate parser.

    Args:
        log_path: Path to the log file
        protocol: Protocol hint (icmp, tcp, udp), or None to auto-detect
        direction: Direction hint for ICMP (rx, tx), or None to auto-detect

    Returns:
        Parsed data structure
    """
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return {"error": f"Log file missing or empty: {log_path}",
                "flows": {"total": 0, "complete": 0},
                "drops": {},
                "latency_us": {}}

    with open(log_path, "r") as f:
        content = f.read()

    # Auto-detect format if not specified
    detected_protocol, detected_mode, detected_direction = detect_log_format(content)

    if protocol is None:
        protocol = detected_protocol
    if direction is None:
        direction = detected_direction

    # Route to appropriate parser
    if protocol == 'icmp':
        from parse_icmp_verbose import parse_icmp_verbose_log
        return parse_icmp_verbose_log(content, direction)

    elif protocol in ('tcp', 'udp'):
        # Reserved for future implementation
        return {
            "error": f"Protocol '{protocol}' parser not yet implemented",
            "flows": {"total": 0, "complete": 0},
            "drops": {},
            "latency_us": {}
        }

    return {
        "error": f"Unknown protocol format in {log_path}",
        "flows": {"total": 0, "complete": 0},
        "drops": {},
        "latency_us": {}
    }


def format_drop_output(receiver: dict, sender: dict, direction: str) -> dict:
    """Format output for focus=drop mode.

    Emphasizes drop statistics, latency only shows total.
    """
    def simplify_latency(data: dict) -> dict:
        """Keep only total latency for drop focus."""
        result = data.copy()
        if 'latency_us' in result and 'total' in result['latency_us']:
            result['latency_us'] = {'total': result['latency_us']['total']}
        return result

    return {
        "receiver": simplify_latency(receiver),
        "sender": simplify_latency(sender),
    }


def format_latency_output(receiver: dict, sender: dict, protocol: str,
                          direction: str) -> dict:
    """Format output for focus=latency mode.

    Full latency segment analysis with data path diagram and percentages.
    """
    def calculate_percentages(latency_data: dict) -> dict:
        """Calculate percentage of each segment relative to total."""
        if not latency_data or 'total' not in latency_data:
            return {}

        total_avg = latency_data.get('total', {}).get('avg', 0)
        if total_avg <= 0:
            return {}

        result = {}
        for key, value in latency_data.items():
            if key == 'total':
                continue
            if isinstance(value, dict) and 'avg' in value:
                segment_avg = value['avg']
                result[value.get('name', key)] = {
                    'avg_us': segment_avg,
                    'pct': round(segment_avg / total_avg * 100, 1)
                }
        result['Total'] = {
            'avg_us': total_avg,
            'pct': 100.0
        }
        return result

    # Build data path diagram based on direction
    if direction == 'rx':
        data_path = {
            "description": "System Network ICMP RX Mode (local responds to remote ping)",
            "path": [
                {"stage": "[0] phy RX", "desc": "ICMP request arrives at physical NIC"},
                {"stage": "→ ReqPath →", "desc": "Request traverses kernel to stack"},
                {"stage": "[1] icmp_rcv", "desc": "ICMP handler receives request"},
                {"stage": "→ Stack →", "desc": "Stack processes and generates reply"},
                {"stage": "[2] ip_send_skb", "desc": "Reply ready to send"},
                {"stage": "→ RepPath →", "desc": "Reply traverses kernel to NIC"},
                {"stage": "[3] phy TX", "desc": "ICMP reply leaves physical NIC"},
            ],
            "diagram": """
Sender Host                                     Receiver Host (measured)
┌──────────┐                                   ┌───────────────────────────────────────┐
│          │     ICMP Request                  │ phy RX ──ReqPath──→ icmp_rcv         │
│   ping ──┼───────────────────────────────────┼─→[0]                  [1]            │
│          │                                   │                        │              │
│          │                                   │                      Stack            │
│          │                                   │                        │              │
│          │     ICMP Reply                    │ phy TX ←─RepPath─── ip_send_skb      │
│   recv ←─┼───────────────────────────────────┼─←[3]                  [2]            │
└──────────┘                                   └───────────────────────────────────────┘
"""
        }
    else:  # tx
        data_path = {
            "description": "System Network ICMP TX Mode (local initiates ping)",
            "path": [
                {"stage": "[0] ip_send_skb", "desc": "Local ping generates ICMP request"},
                {"stage": "→ ReqPath →", "desc": "Request traverses kernel to NIC"},
                {"stage": "[1] phy TX", "desc": "ICMP request leaves physical NIC"},
                {"stage": "→ External →", "desc": "Network + remote processing"},
                {"stage": "[2] phy RX", "desc": "ICMP reply arrives at physical NIC"},
                {"stage": "→ RepPath →", "desc": "Reply traverses kernel to stack"},
                {"stage": "[3] ping_rcv", "desc": "Ping handler receives reply"},
            ],
            "diagram": """
Sender Host (measured)                          Receiver Host
┌───────────────────────────────────────┐      ┌──────────┐
│ ip_send_skb ──ReqPath──→ phy TX      │      │          │
│     [0]                    [1]───────┼──────┼─→ recv   │
│                                      │      │          │
│                External (network)    │      │          │
│                                      │      │          │
│ ping_rcv ←──RepPath─── phy RX        │      │          │
│     [3]                    [2]←──────┼──────┼── reply  │
└───────────────────────────────────────┘      └──────────┘
"""
        }

    # Calculate segment percentages for both hosts
    receiver_segments = calculate_percentages(receiver.get('latency_us', {}))
    sender_segments = calculate_percentages(sender.get('latency_us', {}))

    # Build latency analysis
    latency_analysis = {
        "data_path": data_path,
        "segment_breakdown": {
            "receiver_host": {
                "role": receiver.get('role', 'primary'),
                "flows_measured": receiver.get('flows', {}).get('complete', 0),
                "segments": receiver_segments
            },
            "sender_host": {
                "role": sender.get('role', 'secondary'),
                "flows_measured": sender.get('flows', {}).get('complete', 0),
                "segments": sender_segments
            }
        },
        "summary": _build_latency_summary(receiver_segments, sender_segments, direction)
    }

    return {
        "receiver": receiver,
        "sender": sender,
        "latency_analysis": latency_analysis
    }


def _build_latency_summary(recv_segments: dict, send_segments: dict,
                           direction: str) -> dict:
    """Build latency summary combining both hosts."""
    summary = {
        "description": "End-to-end latency breakdown for system network path"
    }

    if direction == 'rx':
        # RX mode: ReqPath + Stack + RepPath
        summary["segments"] = ["ReqPath", "Stack", "RepPath"]
        summary["notes"] = [
            "ReqPath: phy RX → icmp_rcv (OVS + kernel network stack)",
            "Stack: icmp_rcv → ip_send_skb (ICMP processing)",
            "RepPath: ip_send_skb → phy TX (kernel + OVS)"
        ]
    else:
        # TX mode: ReqPath + External + RepPath
        summary["segments"] = ["ReqPath", "External", "RepPath"]
        summary["notes"] = [
            "ReqPath: ip_send_skb → phy TX (kernel + OVS)",
            "External: phy TX → phy RX (network + remote host)",
            "RepPath: phy RX → ping_rcv (OVS + kernel)"
        ]

    # Calculate average percentages across both hosts
    combined = {}
    for seg in summary["segments"]:
        recv_val = recv_segments.get(seg, {})
        send_val = send_segments.get(seg, {})
        if recv_val and send_val:
            combined[seg] = {
                "avg_us": round((recv_val.get('avg_us', 0) + send_val.get('avg_us', 0)) / 2, 1),
                "pct": round((recv_val.get('pct', 0) + send_val.get('pct', 0)) / 2, 1)
            }
        elif recv_val:
            combined[seg] = recv_val
        elif send_val:
            combined[seg] = send_val

    summary["combined_averages"] = combined
    return summary


def parse_system_drop_logs(measurement_dir: str,
                           protocol: str = 'icmp',
                           direction: str = 'rx',
                           focus: str = 'drop',
                           output_mode: str = 'verbose') -> dict:
    """Parse all logs in a system-network-path-tracer measurement directory.

    Args:
        measurement_dir: Directory containing log files
        protocol: Protocol type (icmp, tcp, udp)
        direction: ICMP direction (rx, tx)
        focus: Measurement focus (drop, latency)
        output_mode: Output mode (verbose, stats)

    Returns:
        Combined measurement results
    """
    receiver_log = os.path.join(measurement_dir, "receiver-host.log")
    sender_log = os.path.join(measurement_dir, "sender-host.log")

    receiver = parse_log_file(receiver_log, protocol, direction)
    sender = parse_log_file(sender_log, protocol, direction)

    receiver["role"] = "primary (traces A→B traffic)"
    sender["role"] = "secondary (traces B→A traffic)"

    # Base result structure
    result = {
        "measurement_type": "system-network-path-tracer",
        "protocol": protocol,
        "direction": direction,
        "focus": focus,
        "output_mode": output_mode,
        "log_files": ["receiver-host.log", "sender-host.log"],
        "measurement_dir": measurement_dir,
    }

    # Format output based on focus mode
    if focus == 'latency':
        formatted = format_latency_output(receiver, sender, protocol, direction)
    else:  # drop
        formatted = format_drop_output(receiver, sender, direction)

    result.update(formatted)
    return result


def generate_terminal_summary(data: dict) -> str:
    """Generate terminal-friendly summary for stdout.

    Args:
        data: Parsed measurement data dictionary

    Returns:
        Clean text summary for terminal display
    """
    lines = []
    receiver = data.get('receiver', {})
    sender = data.get('sender', {})
    focus = data.get('focus', 'drop')
    direction = data.get('direction', 'rx')

    recv_flows = receiver.get('flows', {})
    send_flows = sender.get('flows', {})
    recv_total = receiver.get('latency_us', {}).get('total', {})
    send_total = sender.get('latency_us', {}).get('total', {})
    recv_drops = receiver.get('drops', {})
    send_drops = sender.get('drops', {})

    lines.append("")
    lines.append("=" * 70)
    lines.append("  SYSTEM NETWORK PATH TRACER REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Protocol: {data.get('protocol', 'icmp').upper()}  |  "
                 f"Direction: {direction.upper()}  |  Focus: {focus}")
    lines.append("")

    # Summary
    lines.append("-" * 70)
    lines.append("  MEASUREMENT SUMMARY")
    lines.append("-" * 70)
    lines.append("")
    lines.append(f"  {'Metric':<25} {'Receiver Host':>18} {'Sender Host':>18}")
    lines.append(f"  {'-'*25} {'-'*18} {'-'*18}")
    lines.append(f"  {'Flows (complete/total)':<25} "
                 f"{recv_flows.get('complete', 0):>9}/{recv_flows.get('total', 0):<8} "
                 f"{send_flows.get('complete', 0):>9}/{send_flows.get('total', 0):<8}")
    lines.append(f"  {'Drop Rate':<25} {receiver.get('drop_rate', 0)*100:>17.1f}% {sender.get('drop_rate', 0)*100:>17.1f}%")
    lines.append(f"  {'Latency Avg (µs)':<25} {recv_total.get('avg', 0):>18.1f} {send_total.get('avg', 0):>18.1f}")
    lines.append(f"  {'Latency Min (µs)':<25} {recv_total.get('min', 0):>18.1f} {send_total.get('min', 0):>18.1f}")
    lines.append(f"  {'Latency Max (µs)':<25} {recv_total.get('max', 0):>18.1f} {send_total.get('max', 0):>18.1f}")
    lines.append("")

    # Drop Statistics
    has_drops = any([
        recv_drops.get(k, 0) > 0 or send_drops.get(k, 0) > 0
        for k in ['internal_request', 'stack_no_reply', 'internal_reply', 'external']
    ])

    if has_drops or focus == 'drop':
        lines.append("-" * 70)
        lines.append("  DROP STATISTICS")
        lines.append("-" * 70)
        lines.append("")

        if direction == 'rx':
            drop_types = [
                ('Internal Request', 'internal_request'),
                ('Stack (no reply)', 'stack_no_reply'),
                ('Internal Reply', 'internal_reply'),
            ]
        else:
            drop_types = [
                ('Internal Request', 'internal_request'),
                ('External', 'external'),
                ('Internal Reply', 'internal_reply'),
            ]

        lines.append(f"  {'Location':<25} {'Receiver':>18} {'Sender':>18}")
        lines.append(f"  {'-'*25} {'-'*18} {'-'*18}")
        for label, key in drop_types:
            recv_val = recv_drops.get(key, 0)
            send_val = send_drops.get(key, 0)
            recv_str = f"*** {recv_val} ***" if recv_val > 0 else str(recv_val)
            send_str = f"*** {send_val} ***" if send_val > 0 else str(send_val)
            lines.append(f"  {label:<25} {recv_str:>18} {send_str:>18}")
        lines.append("")

    # Latency Breakdown (for latency focus)
    if focus == 'latency':
        latency_analysis = data.get('latency_analysis', {})
        segment_breakdown = latency_analysis.get('segment_breakdown', {})

        lines.append("-" * 70)
        lines.append("  LATENCY BREAKDOWN")
        lines.append("-" * 70)
        lines.append("")

        for host_key, host_name in [('receiver_host', 'Receiver Host'), ('sender_host', 'Sender Host')]:
            breakdown = segment_breakdown.get(host_key, {})
            segments = breakdown.get('segments', {})
            if segments:
                lines.append(f"  {host_name} ({breakdown.get('flows_measured', 0)} flows):")
                lines.append(f"    {'Segment':<15} {'Avg (µs)':>12} {'% of Total':>12}")
                lines.append(f"    {'-'*15} {'-'*12} {'-'*12}")
                for seg_name, seg_data in segments.items():
                    if seg_name != 'Total':
                        lines.append(f"    {seg_name:<15} {seg_data.get('avg_us', 0):>12.1f} {seg_data.get('pct', 0):>11.1f}%")
                total_data = segments.get('Total', {})
                lines.append(f"    {'─'*15} {'─'*12} {'─'*12}")
                lines.append(f"    {'TOTAL':<15} {total_data.get('avg_us', 0):>12.1f} {total_data.get('pct', 0):>11.1f}%")
                lines.append("")

    # Key Findings
    lines.append("-" * 70)
    lines.append("  KEY FINDINGS")
    lines.append("-" * 70)
    lines.append("")

    if has_drops:
        lines.append("  ⚠️  PACKET DROPS DETECTED:")
        for key in ['internal_request', 'stack_no_reply', 'internal_reply', 'external']:
            if recv_drops.get(key, 0) > 0:
                lines.append(f"      - Receiver {key}: {recv_drops[key]} drops")
            if send_drops.get(key, 0) > 0:
                lines.append(f"      - Sender {key}: {send_drops[key]} drops")
    else:
        lines.append("  ✅  No packet drops detected")

    avg_latency = (recv_total.get('avg', 0) + send_total.get('avg', 0)) / 2
    if avg_latency > 1000:
        lines.append(f"  ⚠️  High latency: {avg_latency:.1f} µs (exceeds 1ms threshold)")
    elif avg_latency > 500:
        lines.append(f"  ℹ️  Moderate latency: {avg_latency:.1f} µs")
    elif avg_latency > 0:
        lines.append(f"  ✅  Low latency: {avg_latency:.1f} µs")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def generate_markdown_report(data: dict) -> str:
    """Generate Markdown report for file output.

    Args:
        data: Parsed measurement data dictionary

    Returns:
        Markdown formatted report string
    """
    lines = []
    receiver = data.get('receiver', {})
    sender = data.get('sender', {})
    focus = data.get('focus', 'drop')
    direction = data.get('direction', 'rx')

    recv_flows = receiver.get('flows', {})
    send_flows = sender.get('flows', {})
    recv_total = receiver.get('latency_us', {}).get('total', {})
    send_total = sender.get('latency_us', {}).get('total', {})
    recv_drops = receiver.get('drops', {})
    send_drops = sender.get('drops', {})

    # Header
    lines.append("# System Network Path Tracer Report")
    lines.append("")
    lines.append(f"**Measurement Directory**: `{data.get('measurement_dir', 'N/A')}`")
    lines.append(f"**Analysis Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Protocol**: {data.get('protocol', 'icmp').upper()} | "
                 f"**Direction**: {direction.upper()} | **Focus**: {focus}")
    lines.append("")

    # Summary Table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Receiver Host | Sender Host |")
    lines.append("|:-------|-------------:|------------:|")
    lines.append(f"| Flows (complete/total) | {recv_flows.get('complete', 0)}/{recv_flows.get('total', 0)} | {send_flows.get('complete', 0)}/{send_flows.get('total', 0)} |")
    lines.append(f"| Drop Rate | {receiver.get('drop_rate', 0)*100:.1f}% | {sender.get('drop_rate', 0)*100:.1f}% |")
    lines.append(f"| Latency Avg | {recv_total.get('avg', 0):.1f} µs | {send_total.get('avg', 0):.1f} µs |")
    lines.append(f"| Latency Range | {recv_total.get('min', 0):.1f}-{recv_total.get('max', 0):.1f} µs | {send_total.get('min', 0):.1f}-{send_total.get('max', 0):.1f} µs |")
    lines.append("")

    # Drop Statistics
    lines.append("## Drop Statistics")
    lines.append("")

    if direction == 'rx':
        drop_types = [
            ('Internal Request', 'internal_request'),
            ('Stack (no reply)', 'stack_no_reply'),
            ('Internal Reply', 'internal_reply'),
        ]
    else:
        drop_types = [
            ('Internal Request', 'internal_request'),
            ('External', 'external'),
            ('Internal Reply', 'internal_reply'),
        ]

    lines.append("| Location | Receiver | Sender |")
    lines.append("|:---------|--------:|---------:|")
    for label, key in drop_types:
        recv_val = recv_drops.get(key, 0)
        send_val = send_drops.get(key, 0)
        recv_str = f"**{recv_val}**" if recv_val > 0 else str(recv_val)
        send_str = f"**{send_val}**" if send_val > 0 else str(send_val)
        lines.append(f"| {label} | {recv_str} | {send_str} |")
    lines.append("")

    # Latency Breakdown (for latency focus)
    if focus == 'latency':
        latency_analysis = data.get('latency_analysis', {})
        segment_breakdown = latency_analysis.get('segment_breakdown', {})
        summary = latency_analysis.get('summary', {})

        lines.append("## Latency Breakdown")
        lines.append("")

        for host_key, host_name in [('receiver_host', 'Receiver Host'), ('sender_host', 'Sender Host')]:
            breakdown = segment_breakdown.get(host_key, {})
            segments = breakdown.get('segments', {})
            if segments:
                lines.append(f"### {host_name}")
                lines.append(f"*{breakdown.get('flows_measured', 0)} flows measured*")
                lines.append("")
                lines.append("| Segment | Avg (µs) | % of Total |")
                lines.append("|:--------|--------:|-----------:|")
                for seg_name, seg_data in segments.items():
                    if seg_name == 'Total':
                        lines.append(f"| **{seg_name}** | **{seg_data.get('avg_us', 0):.1f}** | **{seg_data.get('pct', 0):.1f}%** |")
                    else:
                        lines.append(f"| {seg_name} | {seg_data.get('avg_us', 0):.1f} | {seg_data.get('pct', 0):.1f}% |")
                lines.append("")

        # Data Path Diagram
        data_path = latency_analysis.get('data_path', {})
        if data_path.get('diagram'):
            lines.append("## Data Path Diagram")
            lines.append("")
            lines.append(f"*{data_path.get('description', '')}*")
            lines.append("")
            lines.append("```")
            lines.append(data_path['diagram'].strip())
            lines.append("```")
            lines.append("")

        # Segment Definitions
        if summary.get('notes'):
            lines.append("## Segment Definitions")
            lines.append("")
            for note in summary['notes']:
                lines.append(f"- {note}")
            lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    lines.append("")

    has_drops = any([
        recv_drops.get(k, 0) > 0 or send_drops.get(k, 0) > 0
        for k in ['internal_request', 'stack_no_reply', 'internal_reply', 'external']
    ])

    if has_drops:
        lines.append("### ⚠️ Packet Drops Detected")
        lines.append("")
        for key in ['internal_request', 'stack_no_reply', 'internal_reply', 'external']:
            if recv_drops.get(key, 0) > 0:
                lines.append(f"- Receiver {key}: **{recv_drops[key]}** drops")
            if send_drops.get(key, 0) > 0:
                lines.append(f"- Sender {key}: **{send_drops[key]}** drops")
        lines.append("")
    else:
        lines.append("✅ No packet drops detected during measurement period.")
        lines.append("")

    avg_latency = (recv_total.get('avg', 0) + send_total.get('avg', 0)) / 2
    if avg_latency > 1000:
        lines.append(f"### ⚠️ High Latency")
        lines.append(f"Average latency ({avg_latency:.1f} µs) exceeds 1ms threshold.")
    elif avg_latency > 500:
        lines.append(f"### ℹ️ Moderate Latency")
        lines.append(f"Average latency: {avg_latency:.1f} µs")
    elif avg_latency > 0:
        lines.append(f"### ✅ Low Latency")
        lines.append(f"Average latency: {avg_latency:.1f} µs (excellent)")
    lines.append("")

    return "\n".join(lines)


def save_report(measurement_dir: str, data: dict) -> str:
    """Save markdown report to measurement directory.

    Returns:
        Path to saved report file
    """
    report_path = os.path.join(measurement_dir, "report.md")
    markdown = generate_markdown_report(data)
    with open(report_path, 'w') as f:
        f.write(markdown)
    return report_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse system network path tracer logs")
    parser.add_argument("measurement_dir", help="Measurement directory")
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp')
    parser.add_argument("--direction", choices=['rx', 'tx'], default='rx')
    parser.add_argument("--focus", choices=['drop', 'latency'], default='drop')
    parser.add_argument("--output-mode", choices=['verbose', 'stats'], default='verbose')
    parser.add_argument("--json", action='store_true', help="Output JSON to stdout")
    parser.add_argument("--no-report", action='store_true', help="Skip saving report.md file")

    args = parser.parse_args()

    result = parse_system_drop_logs(
        args.measurement_dir,
        protocol=args.protocol,
        direction=args.direction,
        focus=args.focus,
        output_mode=args.output_mode
    )

    if args.json:
        # JSON mode: output JSON only
        print(json.dumps(result, indent=2))
    else:
        # Default mode: save report.md + print terminal summary
        if not args.no_report:
            report_path = save_report(args.measurement_dir, result)
        print(generate_terminal_summary(result))
        if not args.no_report:
            print(f"\n  Report saved to: {report_path}")
