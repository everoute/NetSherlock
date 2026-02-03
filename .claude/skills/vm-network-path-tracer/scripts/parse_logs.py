#!/usr/bin/env python3
"""Parse VM network path tracer log files (v2).

Routes to protocol-specific parsers based on log content detection.

Supported formats:
- ICMP verbose: icmp_path_tracer.py with --verbose
- TCP/UDP verbose: tcp_path_tracer.py / udp_path_tracer.py --verbose (reserved)
- TCP/UDP stats: tcp_path_tracer.py / udp_path_tracer.py --stats-interval (reserved)
"""

import json
import os
import sys
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

    return {
        "measurement_type": "vm-network-path-tracer",
        "protocol": protocol,
        "focus": focus,
        "output_mode": output_mode,
        "sender": sender,
        "receiver": receiver,
        "log_files": ["sender-host.log", "receiver-host.log"],
        "measurement_dir": measurement_dir,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse VM network path tracer logs")
    parser.add_argument("measurement_dir", help="Measurement directory")
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp')
    parser.add_argument("--focus", choices=['drop', 'latency'], default='drop')
    parser.add_argument("--output-mode", choices=['verbose', 'stats'], default='verbose')

    args = parser.parse_args()

    result = parse_vm_drop_logs(
        args.measurement_dir,
        protocol=args.protocol,
        focus=args.focus,
        output_mode=args.output_mode
    )
    print(json.dumps(result, indent=2))
