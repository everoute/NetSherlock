#!/usr/bin/env python3
"""Parse VM network path tracer log files (v2).

Routes to protocol-specific parsers based on log content detection.
Outputs readable Markdown reports (or JSON with --json flag).

Focus modes:
- drop: Emphasize drop statistics, latency only shows total
- latency: Full latency segment analysis with data path diagram and percentages
           Shows host + physical network latency (excludes VM virtualization & VM internal)

Supported formats:
- ICMP verbose: icmp_path_tracer.py with --verbose
- TCP/UDP verbose: tcp_path_tracer.py / udp_path_tracer.py --verbose (reserved)
- TCP/UDP stats: tcp_path_tracer.py / udp_path_tracer.py --stats-interval (reserved)
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional, Tuple


def detect_log_format(content: str) -> Tuple[str, str]:
    """Detect protocol and output mode from log content.

    Returns: (protocol, output_mode)
    """
    # VM boundary tools detection
    if 'ICMP Drop Detector' in content or 'ICMP Path Tracer' in content:
        return ('icmp', 'verbose')
    elif 'TCP Path Tracer' in content:
        if 'Mode: Stats' in content:
            return ('tcp', 'stats')
        return ('tcp', 'verbose')
    elif 'UDP Path Tracer' in content:
        if 'Mode: Stats' in content:
            return ('udp', 'stats')
        return ('udp', 'verbose')

    return ('unknown', 'unknown')


def parse_log_file(log_path: str, protocol: Optional[str] = None) -> dict:
    """Parse a single log file using the appropriate parser.

    Args:
        log_path: Path to the log file
        protocol: Protocol hint (icmp, tcp, udp), or None to auto-detect

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
    detected_protocol, detected_mode = detect_log_format(content)

    if protocol is None:
        protocol = detected_protocol

    # Route to appropriate parser
    if protocol == 'icmp':
        from parse_icmp_verbose import parse_icmp_verbose_log
        return parse_icmp_verbose_log(content)

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


def format_drop_output(sender: dict, receiver: dict) -> dict:
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
        "sender": simplify_latency(sender),
        "receiver": simplify_latency(receiver),
    }


def format_latency_output(sender: dict, receiver: dict, protocol: str) -> dict:
    """Format output for focus=latency mode.

    Full latency segment analysis with data path diagram and percentages.
    Shows host + physical network latency (excludes VM internal).
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

    # Build VM network data path diagram
    data_path = {
        "description": "VM Network Path Tracer - Host Boundary Monitoring",
        "coverage": "Measures: Sender Host OVS + Physical Network + Receiver Host OVS",
        "excludes": "VM virtualization overhead (vhost/QEMU) and VM internal processing",
        "path": [
            {"stage": "Sender VM", "desc": "VM generates ICMP request (not measured)"},
            {"stage": "─── virtio ───→", "desc": "VM to vhost (not measured)"},
            {"stage": "[S0] vnet RX", "desc": "Request enters sender host vnet interface"},
            {"stage": "→ ReqInternal →", "desc": "Sender: vnet → OVS → phy (measured)"},
            {"stage": "[S1] phy TX", "desc": "Request leaves sender physical NIC"},
            {"stage": "════ Network ════", "desc": "Physical network traversal"},
            {"stage": "[R0] phy RX", "desc": "Request arrives at receiver physical NIC"},
            {"stage": "→ ReqInternal →", "desc": "Receiver: phy → OVS → vnet (measured)"},
            {"stage": "[R1] vnet TX", "desc": "Request enters receiver vnet interface"},
            {"stage": "─── virtio ───→", "desc": "vhost to VM (not measured)"},
            {"stage": "Receiver VM", "desc": "VM processes and generates reply (not measured)"},
            {"stage": "─── virtio ───→", "desc": "VM to vhost (not measured)"},
            {"stage": "[R2] vnet RX", "desc": "Reply enters receiver vnet interface"},
            {"stage": "→ RepInternal →", "desc": "Receiver: vnet → OVS → phy (measured)"},
            {"stage": "[R3] phy TX", "desc": "Reply leaves receiver physical NIC"},
            {"stage": "════ Network ════", "desc": "Physical network traversal"},
            {"stage": "[S2] phy RX", "desc": "Reply arrives at sender physical NIC"},
            {"stage": "→ RepInternal →", "desc": "Sender: phy → OVS → vnet (measured)"},
            {"stage": "[S3] vnet TX", "desc": "Reply enters sender vnet interface"},
            {"stage": "─── virtio ───→", "desc": "vhost to VM (not measured)"},
            {"stage": "Sender VM", "desc": "VM receives reply (not measured)"},
        ],
        "diagram": """
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              VM Network Latency Measurement                              │
│                     (Host Boundary Monitoring - excludes VM internal)                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  Sender VM         Sender Host                        Receiver Host        Receiver VM  │
│  ┌───────┐   ┌─────────────────────────┐  Network  ┌─────────────────────────┐  ┌───────┐
│  │       │   │ vnet35    enp24s0f0np0  │          │ enp24s0f0np0    vnet130 │  │       │
│  │ ping ─┼───┼─[S0]─ReqInt─→[S1]──────┼──────────┼────→[R0]─ReqInt─→[R1]───┼──┼─→recv │
│  │       │   │                         │          │                         │  │       │
│  │       │   │      (OVS datapath)     │          │      (OVS datapath)     │  │ (VM)  │
│  │       │   │                         │          │                         │  │       │
│  │ recv←─┼───┼─[S3]←─RepInt─[S2]←─────┼──────────┼────←[R3]←─RepInt─[R2]←──┼──┼─reply │
│  └───────┘   └─────────────────────────┘          └─────────────────────────┘  └───────┘
│                                                                                         │
│  Legend: [Sn]=Sender probe point, [Rn]=Receiver probe point                            │
│          ReqInt=Request Internal (OVS), RepInt=Reply Internal (OVS)                    │
│          External = Network + Remote Host + Remote VM processing                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘
"""
    }

    # Calculate segment percentages
    sender_segments = calculate_percentages(sender.get('latency_us', {}))
    receiver_segments = calculate_percentages(receiver.get('latency_us', {}))

    # Build latency analysis
    latency_analysis = {
        "data_path": data_path,
        "segment_breakdown": {
            "sender_host": {
                "boundary": sender.get('boundary', 'vnet→phy (VM outbound)'),
                "flows_measured": sender.get('flows', {}).get('complete', 0),
                "segments": sender_segments,
                "notes": [
                    "ReqInternal: vnet RX → OVS → phy TX (request leaving VM)",
                    "External: phy TX → phy RX (network + receiver host + receiver VM)",
                    "RepInternal: phy RX → OVS → vnet TX (reply returning to VM)"
                ]
            },
            "receiver_host": {
                "boundary": receiver.get('boundary', 'phy→vnet (VM inbound)'),
                "flows_measured": receiver.get('flows', {}).get('complete', 0),
                "segments": receiver_segments,
                "notes": [
                    "ReqInternal: phy RX → OVS → vnet TX (request entering VM)",
                    "External: vnet TX → vnet RX (VM internal processing)",
                    "RepInternal: vnet RX → OVS → phy TX (reply leaving VM)"
                ]
            }
        },
        "summary": _build_vm_latency_summary(sender_segments, receiver_segments)
    }

    return {
        "sender": sender,
        "receiver": receiver,
        "latency_analysis": latency_analysis
    }


def _build_vm_latency_summary(sender_segments: dict, receiver_segments: dict) -> dict:
    """Build VM latency summary combining both hosts."""
    summary = {
        "description": "End-to-end VM network latency breakdown",
        "coverage": "Host OVS + Physical Network (excludes VM virtualization & VM internal)",
        "segments": ["ReqInternal", "External", "RepInternal"],
        "attribution": {
            "measured": [
                "Sender Host: OVS datapath (vnet↔phy)",
                "Receiver Host: OVS datapath (phy↔vnet)",
                "Physical Network: wire latency"
            ],
            "not_measured": [
                "VM virtualization: vhost/QEMU overhead",
                "VM internal: guest kernel + application"
            ]
        }
    }

    # Calculate combined statistics
    combined = {}
    for seg in summary["segments"]:
        send_val = sender_segments.get(seg, {})
        recv_val = receiver_segments.get(seg, {})

        values = []
        if send_val and 'avg_us' in send_val:
            values.append(send_val['avg_us'])
        if recv_val and 'avg_us' in recv_val:
            values.append(recv_val['avg_us'])

        if values:
            combined[seg] = {
                "sender_avg_us": send_val.get('avg_us', 0) if send_val else 0,
                "sender_pct": send_val.get('pct', 0) if send_val else 0,
                "receiver_avg_us": recv_val.get('avg_us', 0) if recv_val else 0,
                "receiver_pct": recv_val.get('pct', 0) if recv_val else 0,
            }

    # Add totals
    sender_total = sender_segments.get('Total', {})
    receiver_total = receiver_segments.get('Total', {})
    combined['Total'] = {
        "sender_avg_us": sender_total.get('avg_us', 0),
        "receiver_avg_us": receiver_total.get('avg_us', 0),
        "note": "Sender total includes External (network + receiver), Receiver total is local only"
    }

    summary["combined_breakdown"] = combined
    return summary


def parse_vm_drop_logs(measurement_dir: str,
                       protocol: str = 'icmp',
                       focus: str = 'drop',
                       output_mode: str = 'verbose') -> dict:
    """Parse all logs in a vm-network-path-tracer measurement directory.

    Args:
        measurement_dir: Directory containing log files
        protocol: Protocol type (icmp, tcp, udp)
        focus: Measurement focus (drop, latency)
        output_mode: Output mode (verbose, stats)

    Returns:
        Combined measurement results
    """
    sender_log = os.path.join(measurement_dir, "sender-host.log")
    receiver_log = os.path.join(measurement_dir, "receiver-host.log")

    sender = parse_log_file(sender_log, protocol)
    receiver = parse_log_file(receiver_log, protocol)

    sender["boundary"] = "vnet→phy (VM outbound)"
    receiver["boundary"] = "phy→vnet (VM inbound)"

    # Base result structure
    result = {
        "measurement_type": "vm-network-path-tracer",
        "protocol": protocol,
        "focus": focus,
        "output_mode": output_mode,
        "log_files": ["sender-host.log", "receiver-host.log"],
        "measurement_dir": measurement_dir,
    }

    # Format output based on focus mode
    if focus == 'latency':
        formatted = format_latency_output(sender, receiver, protocol)
    else:  # drop
        formatted = format_drop_output(sender, receiver)

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
    sender = data.get('sender', {})
    receiver = data.get('receiver', {})
    focus = data.get('focus', 'drop')

    send_flows = sender.get('flows', {})
    recv_flows = receiver.get('flows', {})
    send_total = sender.get('latency_us', {}).get('total', {})
    recv_total = receiver.get('latency_us', {}).get('total', {})
    send_drops = sender.get('drops', {})
    recv_drops = receiver.get('drops', {})

    lines.append("")
    lines.append("=" * 70)
    lines.append("  VM NETWORK PATH TRACER REPORT")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"  Protocol: {data.get('protocol', 'icmp').upper()}  |  Focus: {focus}")
    lines.append("")

    # Summary
    lines.append("-" * 70)
    lines.append("  MEASUREMENT SUMMARY")
    lines.append("-" * 70)
    lines.append("")
    lines.append(f"  {'Metric':<25} {'Sender Host':>18} {'Receiver Host':>18}")
    lines.append(f"  {'-'*25} {'-'*18} {'-'*18}")
    lines.append(f"  {'Boundary':<25} {'vnet→phy':>18} {'phy→vnet':>18}")
    lines.append(f"  {'Flows (complete/total)':<25} "
                 f"{send_flows.get('complete', 0):>9}/{send_flows.get('total', 0):<8} "
                 f"{recv_flows.get('complete', 0):>9}/{recv_flows.get('total', 0):<8}")
    lines.append(f"  {'Drop Rate':<25} {sender.get('drop_rate', 0)*100:>17.1f}% {receiver.get('drop_rate', 0)*100:>17.1f}%")
    lines.append(f"  {'Latency Avg (µs)':<25} {send_total.get('avg', 0):>18.1f} {recv_total.get('avg', 0):>18.1f}")
    lines.append(f"  {'Latency Min (µs)':<25} {send_total.get('min', 0):>18.1f} {recv_total.get('min', 0):>18.1f}")
    lines.append(f"  {'Latency Max (µs)':<25} {send_total.get('max', 0):>18.1f} {recv_total.get('max', 0):>18.1f}")
    lines.append("")

    # Drop Statistics
    has_drops = any([
        send_drops.get(k, 0) > 0 or recv_drops.get(k, 0) > 0
        for k in ['req_internal', 'external', 'rep_internal']
    ])

    if has_drops or focus == 'drop':
        lines.append("-" * 70)
        lines.append("  DROP STATISTICS")
        lines.append("-" * 70)
        lines.append("")

        drop_types = [
            ('Request Internal (OVS)', 'req_internal'),
            ('External (network/VM)', 'external'),
            ('Reply Internal (OVS)', 'rep_internal'),
        ]

        lines.append(f"  {'Location':<25} {'Sender':>18} {'Receiver':>18}")
        lines.append(f"  {'-'*25} {'-'*18} {'-'*18}")
        for label, key in drop_types:
            send_val = send_drops.get(key, 0)
            recv_val = recv_drops.get(key, 0)
            send_str = f"*** {send_val} ***" if send_val > 0 else str(send_val)
            recv_str = f"*** {recv_val} ***" if recv_val > 0 else str(recv_val)
            lines.append(f"  {label:<25} {send_str:>18} {recv_str:>18}")
        lines.append("")

    # Latency Breakdown (for latency focus)
    if focus == 'latency':
        latency_analysis = data.get('latency_analysis', {})
        segment_breakdown = latency_analysis.get('segment_breakdown', {})

        lines.append("-" * 70)
        lines.append("  LATENCY BREAKDOWN (Host Boundary Only)")
        lines.append("-" * 70)
        lines.append("")
        lines.append("  Note: Excludes VM virtualization (vhost/QEMU) and VM internal processing")
        lines.append("")

        for host_key, host_name in [('sender_host', 'Sender Host'), ('receiver_host', 'Receiver Host')]:
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
        for key, label in [('req_internal', 'ReqInternal'), ('external', 'External'), ('rep_internal', 'RepInternal')]:
            if send_drops.get(key, 0) > 0:
                lines.append(f"      - Sender {label}: {send_drops[key]} drops")
            if recv_drops.get(key, 0) > 0:
                lines.append(f"      - Receiver {label}: {recv_drops[key]} drops")
    else:
        lines.append("  ✅  No packet drops detected")

    avg_latency = (send_total.get('avg', 0) + recv_total.get('avg', 0)) / 2
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

    # Header
    lines.append("# VM Network Path Tracer Report")
    lines.append("")
    lines.append(f"**Measurement Directory**: `{data.get('measurement_dir', 'N/A')}`")
    lines.append(f"**Analysis Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Configuration
    lines.append("## Configuration")
    lines.append("")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Protocol | {data.get('protocol', 'icmp').upper()} |")
    lines.append(f"| Focus | {data.get('focus', 'drop')} |")
    lines.append(f"| Output Mode | {data.get('output_mode', 'verbose')} |")
    lines.append("")

    sender = data.get('sender', {})
    receiver = data.get('receiver', {})

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Sender Host | Receiver Host |")
    lines.append("|--------|-------------|---------------|")

    # Boundary
    lines.append(f"| Boundary | {sender.get('boundary', 'vnet→phy')} | {receiver.get('boundary', 'phy→vnet')} |")

    # Flows
    send_flows = sender.get('flows', {})
    recv_flows = receiver.get('flows', {})
    lines.append(f"| Flows (total/complete) | {send_flows.get('total', 0)}/{send_flows.get('complete', 0)} | {recv_flows.get('total', 0)}/{recv_flows.get('complete', 0)} |")

    # Drop rate
    send_drop = sender.get('drop_rate', 0) * 100
    recv_drop = receiver.get('drop_rate', 0) * 100
    lines.append(f"| Drop Rate | {send_drop:.1f}% | {recv_drop:.1f}% |")

    # Total latency
    send_total = sender.get('latency_us', {}).get('total', {})
    recv_total = receiver.get('latency_us', {}).get('total', {})
    lines.append(f"| Total Latency (avg) | {send_total.get('avg', 0):.1f} µs | {recv_total.get('avg', 0):.1f} µs |")
    lines.append(f"| Latency Range | {send_total.get('min', 0):.1f}-{send_total.get('max', 0):.1f} µs | {recv_total.get('min', 0):.1f}-{recv_total.get('max', 0):.1f} µs |")
    lines.append("")

    # Drop Statistics
    lines.append("## Drop Statistics")
    lines.append("")
    lines.append("| Drop Location | Sender Host | Receiver Host |")
    lines.append("|---------------|-------------|---------------|")

    send_drops = sender.get('drops', {})
    recv_drops = receiver.get('drops', {})

    drop_types = [
        ('Request Internal (OVS forward)', 'req_internal'),
        ('External (network/remote)', 'external'),
        ('Reply Internal (OVS forward)', 'rep_internal'),
    ]

    for label, key in drop_types:
        send_val = send_drops.get(key, 0)
        recv_val = recv_drops.get(key, 0)
        send_marker = f"**{send_val}**" if send_val > 0 else str(send_val)
        recv_marker = f"**{recv_val}**" if recv_val > 0 else str(recv_val)
        lines.append(f"| {label} | {send_marker} | {recv_marker} |")
    lines.append("")

    # Focus-specific sections
    focus = data.get('focus', 'drop')

    if focus == 'latency':
        # Latency Breakdown
        latency_analysis = data.get('latency_analysis', {})
        segment_breakdown = latency_analysis.get('segment_breakdown', {})

        lines.append("## Latency Breakdown")
        lines.append("")
        lines.append("> **Note**: This measurement covers **host OVS datapath and physical network only**.")
        lines.append("> VM virtualization overhead (vhost/QEMU) and VM internal processing are **not measured**.")
        lines.append("")

        # Sender host segments
        send_breakdown = segment_breakdown.get('sender_host', {})
        if send_breakdown.get('segments'):
            lines.append(f"### Sender Host ({send_breakdown.get('boundary', 'vnet→phy')})")
            lines.append(f"*Flows measured: {send_breakdown.get('flows_measured', 0)}*")
            lines.append("")
            lines.append("| Segment | Avg (µs) | % of Total |")
            lines.append("|---------|----------|------------|")
            for seg_name, seg_data in send_breakdown['segments'].items():
                if seg_name == 'Total':
                    lines.append(f"| **{seg_name}** | **{seg_data.get('avg_us', 0):.1f}** | **{seg_data.get('pct', 0):.1f}%** |")
                else:
                    lines.append(f"| {seg_name} | {seg_data.get('avg_us', 0):.1f} | {seg_data.get('pct', 0):.1f}% |")
            lines.append("")

            # Add segment notes
            if send_breakdown.get('notes'):
                lines.append("*Segment definitions:*")
                for note in send_breakdown['notes']:
                    lines.append(f"- {note}")
                lines.append("")

        # Receiver host segments
        recv_breakdown = segment_breakdown.get('receiver_host', {})
        if recv_breakdown.get('segments'):
            lines.append(f"### Receiver Host ({recv_breakdown.get('boundary', 'phy→vnet')})")
            lines.append(f"*Flows measured: {recv_breakdown.get('flows_measured', 0)}*")
            lines.append("")
            lines.append("| Segment | Avg (µs) | % of Total |")
            lines.append("|---------|----------|------------|")
            for seg_name, seg_data in recv_breakdown['segments'].items():
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

        # Coverage summary
        summary = latency_analysis.get('summary', {})
        attribution = summary.get('attribution', {})
        if attribution:
            lines.append("## Measurement Coverage")
            lines.append("")
            lines.append("### ✅ Measured")
            for item in attribution.get('measured', []):
                lines.append(f"- {item}")
            lines.append("")
            lines.append("### ❌ Not Measured")
            for item in attribution.get('not_measured', []):
                lines.append(f"- {item}")
            lines.append("")

    # Findings section
    lines.append("## Key Findings")
    lines.append("")

    # Check for issues
    has_drops = any([
        send_drops.get(k, 0) > 0 or recv_drops.get(k, 0) > 0
        for k in ['req_internal', 'external', 'rep_internal']
    ])

    if has_drops:
        lines.append("### ⚠️ Packet Drops Detected")
        lines.append("")
        for key, label in [('req_internal', 'Request Internal'), ('external', 'External'), ('rep_internal', 'Reply Internal')]:
            if send_drops.get(key, 0) > 0:
                lines.append(f"- **Sender {label}**: {send_drops[key]} drops")
            if recv_drops.get(key, 0) > 0:
                lines.append(f"- **Receiver {label}**: {recv_drops[key]} drops")
        lines.append("")

        # Add interpretation
        if send_drops.get('req_internal', 0) > 0 or recv_drops.get('req_internal', 0) > 0:
            lines.append("*Request Internal drops indicate OVS forwarding issues on the request path.*")
        if send_drops.get('external', 0) > 0 or recv_drops.get('external', 0) > 0:
            lines.append("*External drops indicate network issues or remote host/VM problems.*")
        if send_drops.get('rep_internal', 0) > 0 or recv_drops.get('rep_internal', 0) > 0:
            lines.append("*Reply Internal drops indicate OVS forwarding issues on the reply path.*")
        lines.append("")
    else:
        lines.append("✅ **No packet drops detected** during measurement period.")
        lines.append("")

    # Latency finding
    avg_latency = (send_total.get('avg', 0) + recv_total.get('avg', 0)) / 2
    if avg_latency > 1000:
        lines.append(f"### ⚠️ High Latency Warning")
        lines.append(f"Average host-boundary latency ({avg_latency:.1f} µs) exceeds 1ms threshold.")
        lines.append("*Note: This excludes VM internal processing time.*")
    elif avg_latency > 500:
        lines.append(f"### ℹ️ Moderate Latency")
        lines.append(f"Average host-boundary latency: {avg_latency:.1f} µs")
    else:
        lines.append(f"### ✅ Low Latency")
        lines.append(f"Average host-boundary latency: {avg_latency:.1f} µs (excellent)")
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

    parser = argparse.ArgumentParser(description="Parse VM network path tracer logs")
    parser.add_argument("measurement_dir", help="Measurement directory")
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp')
    parser.add_argument("--focus", choices=['drop', 'latency'], default='drop')
    parser.add_argument("--output-mode", choices=['verbose', 'stats'], default='verbose')
    parser.add_argument("--json", action='store_true', help="Output JSON to stdout")
    parser.add_argument("--no-report", action='store_true', help="Skip saving report.md file")

    args = parser.parse_args()

    result = parse_vm_drop_logs(
        args.measurement_dir,
        protocol=args.protocol,
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
