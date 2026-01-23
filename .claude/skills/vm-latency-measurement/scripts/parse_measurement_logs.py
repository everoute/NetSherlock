#!/usr/bin/env python3
"""Parse BPF measurement logs and output structured JSON.

This script parses the output from 8 BPF measurement tools and produces
a JSON structure with segment latencies and total RTT.

Usage:
    python parse_measurement_logs.py <measurement_dir>

Example:
    python parse_measurement_logs.py ./measurement-20240115-143000
"""

import json
import os
import re
import sys
from pathlib import Path


def parse_kernel_icmp_rtt_log(filepath: Path, is_sender: bool = True) -> dict:
    """Parse kernel_icmp_rtt.py output.

    Sample output:
        Total Path 1:  15.234 us
        Total Path 2:  17.456 us
        Inter-Path Latency (P1 end -> P2 start): 550.123 us
        Total RTT (Path1 Start to Path2 End): 582.813 us
    """
    result = {
        "path1": [],
        "path2": [],
        "inter_path": [],
        "total_rtt": [],
    }

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        for line in f:
            # Total Path 1:  15.234 us
            if "Total Path 1:" in line:
                match = re.search(r"Total Path 1:\s+([\d.]+)\s+us", line)
                if match:
                    result["path1"].append(float(match.group(1)))
            # Total Path 2:  17.456 us
            elif "Total Path 2:" in line:
                match = re.search(r"Total Path 2:\s+([\d.]+)\s+us", line)
                if match:
                    result["path2"].append(float(match.group(1)))
            # Inter-Path Latency (P1 end -> P2 start): 550.123 us
            elif "Inter-Path" in line:
                match = re.search(r"Inter-Path[^:]+:\s+([\d.]+)\s+us", line)
                if match:
                    result["inter_path"].append(float(match.group(1)))
            # Total RTT (Path1 Start to Path2 End): 582.813 us
            elif "Total RTT" in line:
                match = re.search(r"Total RTT[^:]+:\s+([\d.]+)\s+us", line)
                if match:
                    result["total_rtt"].append(float(match.group(1)))

    return result


def parse_icmp_drop_detector_log(filepath: Path) -> dict:
    """Parse icmp_drop_detector.py output.

    Sample output formats:
        Format 1: Latency: ReqInternal=15.234 us | External=429.700 us | RepInternal=12.456 us | Total=457.390 us
        Format 2: Latency(us): ReqInternal=55.0  External=294.1  RepInternal=49.5  Total=398.6
    """
    result = {
        "req_internal": [],
        "external": [],
        "rep_internal": [],
        "total": [],
    }

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        for line in f:
            if "Latency" in line and "ReqInternal=" in line:
                # ReqInternal=15.234 (with or without 'us')
                match = re.search(r"ReqInternal=([\d.]+)", line)
                if match:
                    result["req_internal"].append(float(match.group(1)))
                # External=429.700
                match = re.search(r"External=([\d.]+)", line)
                if match:
                    result["external"].append(float(match.group(1)))
                # RepInternal=12.456
                match = re.search(r"RepInternal=([\d.]+)", line)
                if match:
                    result["rep_internal"].append(float(match.group(1)))
                # Total=457.390
                match = re.search(r"Total=([\d.]+)", line)
                if match:
                    result["total"].append(float(match.group(1)))

    return result


def parse_tun_tx_to_kvm_irq_log(filepath: Path) -> dict:
    """Parse tun_tx_to_kvm_irq.py output.

    Sample output formats:
        1. Per-packet total line (preferred, after each Stage 5):
           -> Total(S1->S5): 0.098ms

        2. Per-stage lines (always present):
           Stage 2 [vhost_signal]: ... Delay=0.031ms ...
           Stage 3 [eventfd_signal]: ... Delay=0.010ms ...
           Stage 4 [irqfd_wakeup]: ... Delay=0.013ms ...
           Stage 5 [posted_int]: ... Delay=0.003ms ...

    If per-packet total lines not found, calculate from per-stage delays.
    """
    result = {
        "total_delay": [],  # in ms
    }

    if not filepath.exists():
        return result

    # First pass: look for per-packet total lines "-> Total(S1->S5): X.XXXms"
    with open(filepath, "r") as f:
        for line in f:
            if "-> Total(S1->S5):" in line:
                match = re.search(r"Total\(S1->S5\):\s+([\d.]+)ms", line)
                if match:
                    result["total_delay"].append(float(match.group(1)))

    # If per-packet totals found, return them
    if result["total_delay"]:
        return result

    # Second pass: calculate from per-stage delays
    # Group by chain using Stage 1 as anchor, sum Stage 2-5 delays
    stage_delays = {}  # chain_id -> {stage: delay_ms}
    current_chain = 0

    with open(filepath, "r") as f:
        for line in f:
            if "Stage 1 [tun_net_xmit]" in line:
                current_chain += 1
                stage_delays[current_chain] = {}
            elif current_chain > 0:
                # Parse Stage 2-5 delays
                for stage in [2, 3, 4, 5]:
                    if f"Stage {stage} [" in line:
                        match = re.search(r"Delay=([\d.]+)ms", line)
                        if match:
                            stage_delays[current_chain][stage] = float(match.group(1))

    # Calculate total delay for complete chains (have Stage 2-5)
    for chain_id, stages in stage_delays.items():
        if 2 in stages and 3 in stages and 4 in stages and 5 in stages:
            total = stages[2] + stages[3] + stages[4] + stages[5]
            result["total_delay"].append(total)

    return result


def parse_kvm_vhost_tun_latency_log(filepath: Path) -> dict:
    """Parse kvm_vhost_tun_latency_details.py output.

    Sample output:
        [14:23:16.827] tid=73868 queue=2 s0=14us s1=5us s2=4us total=23us
        Exact averages (us): S0=14.750, S1=3.500, S2=3.250, Total=21.500
    """
    result = {
        "s0": [],
        "s1": [],
        "s2": [],
        "total": [],
    }

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        content = f.read()

        # Try to parse "Exact averages" first
        match = re.search(r"Exact averages.*Total=([\d.]+)", content)
        if match:
            result["total"].append(float(match.group(1)))
        else:
            # Parse individual lines
            for line in content.splitlines():
                # s0=14us s1=5us s2=4us total=23us
                match = re.search(r"total=([\d.]+)\s*us", line, re.IGNORECASE)
                if match:
                    result["total"].append(float(match.group(1)))

    return result


def avg(values: list) -> float:
    """Calculate average of a list, return 0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def parse_all_logs(measurement_dir: Path) -> dict:
    """Parse all measurement logs and calculate segments."""

    # Parse sender VM log
    sender_vm = parse_kernel_icmp_rtt_log(
        measurement_dir / "send-vm-icmp.log", is_sender=True
    )

    # Parse receiver VM log
    receiver_vm = parse_kernel_icmp_rtt_log(
        measurement_dir / "recv-vm-icmp.log", is_sender=False
    )

    # Parse sender host icmp_drop_detector log
    sender_host = parse_icmp_drop_detector_log(
        measurement_dir / "send-host-icmp.log"
    )

    # Parse receiver host icmp_drop_detector log
    receiver_host = parse_icmp_drop_detector_log(
        measurement_dir / "recv-host-icmp.log"
    )

    # Parse sender host tun_tx_to_kvm_irq log (for L segment)
    sender_vhost_rx = parse_tun_tx_to_kvm_irq_log(
        measurement_dir / "send-host-vhost-rx.log"
    )

    # Parse receiver host tun_tx_to_kvm_irq log (for E segment)
    receiver_vhost_rx = parse_tun_tx_to_kvm_irq_log(
        measurement_dir / "recv-host-vhost-rx.log"
    )

    # Parse sender host kvm_vhost_tun_latency log (for B_1 segment)
    sender_kvm_tun = parse_kvm_vhost_tun_latency_log(
        measurement_dir / "send-host-kvm-tun.log"
    )

    # Parse receiver host kvm_vhost_tun_latency log (for I_1 segment)
    receiver_kvm_tun = parse_kvm_vhost_tun_latency_log(
        measurement_dir / "recv-host-kvm-tun.log"
    )

    # Calculate segments
    A = avg(sender_vm["path1"])
    M = avg(sender_vm["path2"])
    total_rtt = avg(sender_vm["total_rtt"])

    F = avg(receiver_vm["path1"])
    G = avg(receiver_vm["inter_path"])
    H = avg(receiver_vm["path2"])

    B = avg(sender_host["req_internal"])
    K = avg(sender_host["rep_internal"])
    sender_external = avg(sender_host["external"])

    D = avg(receiver_host["req_internal"])
    I = avg(receiver_host["rep_internal"])
    receiver_host_total = avg(receiver_host["total"])

    # E and L are in ms, convert to us
    E = avg(receiver_vhost_rx["total_delay"]) * 1000
    L = avg(sender_vhost_rx["total_delay"]) * 1000

    B_1 = avg(sender_kvm_tun["total"])
    I_1 = avg(receiver_kvm_tun["total"])

    # Calculate derived segment: Physical Network (C + J)
    C_J = sender_external - receiver_host_total if receiver_host_total > 0 else 0

    # If total_rtt not parsed, calculate from segments
    if total_rtt == 0:
        total_rtt = A + B + C_J + D + E + F + G + H + I + K + L + M

    # Build result
    result = {
        "total_rtt_us": round(total_rtt, 3),
        "segments": {
            "A": round(A, 3),
            "B": round(B, 3),
            "B_1": round(B_1, 3),
            "C_J": round(C_J, 3),
            "D": round(D, 3),
            "E": round(E, 3),
            "F": round(F, 3),
            "G": round(G, 3),
            "H": round(H, 3),
            "I": round(I, 3),
            "I_1": round(I_1, 3),
            "K": round(K, 3),
            "L": round(L, 3),
            "M": round(M, 3),
        },
        "log_files": [
            "send-vm-icmp.log",
            "recv-vm-icmp.log",
            "send-host-icmp.log",
            "recv-host-icmp.log",
            "send-host-vhost-rx.log",
            "recv-host-vhost-rx.log",
            "send-host-kvm-tun.log",
            "recv-host-kvm-tun.log",
        ],
        "measurement_dir": str(measurement_dir),
        "raw_data": {
            "sender_vm": {
                "path1_samples": len(sender_vm["path1"]),
                "total_rtt_samples": len(sender_vm["total_rtt"]),
            },
            "receiver_vm": {
                "path1_samples": len(receiver_vm["path1"]),
            },
            "sender_host": {
                "samples": len(sender_host["req_internal"]),
                "external_avg": round(sender_external, 3),
            },
            "receiver_host": {
                "samples": len(receiver_host["req_internal"]),
                "total_avg": round(receiver_host_total, 3),
            },
        },
    }

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_measurement_logs.py <measurement_dir>", file=sys.stderr)
        sys.exit(1)

    measurement_dir = Path(sys.argv[1])

    if not measurement_dir.exists():
        print(f"Error: Directory not found: {measurement_dir}", file=sys.stderr)
        sys.exit(1)

    result = parse_all_logs(measurement_dir)

    # Output JSON
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
