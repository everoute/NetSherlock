#!/usr/bin/env python3
"""Parse system network path tracer log files (v2).

Routes to protocol-specific parsers based on log content detection.

Supported formats:
- ICMP verbose: system_icmp_path_tracer.py with --verbose
- TCP/UDP verbose: system_tcp_path_tracer.py / system_udp_path_tracer.py --verbose (reserved)
- TCP/UDP stats: system_tcp_path_tracer.py / system_udp_path_tracer.py --stats-interval (reserved)
"""

import json
import os
import sys
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

    return {
        "measurement_type": "system-network-path-tracer",
        "protocol": protocol,
        "direction": direction,
        "focus": focus,
        "output_mode": output_mode,
        "receiver": receiver,
        "sender": sender,
        "log_files": ["receiver-host.log", "sender-host.log"],
        "measurement_dir": measurement_dir,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse system network path tracer logs")
    parser.add_argument("measurement_dir", help="Measurement directory")
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp')
    parser.add_argument("--direction", choices=['rx', 'tx'], default='rx')
    parser.add_argument("--focus", choices=['drop', 'latency'], default='drop')
    parser.add_argument("--output-mode", choices=['verbose', 'stats'], default='verbose')

    args = parser.parse_args()

    result = parse_system_drop_logs(
        args.measurement_dir,
        protocol=args.protocol,
        direction=args.direction,
        focus=args.focus,
        output_mode=args.output_mode
    )
    print(json.dumps(result, indent=2))
