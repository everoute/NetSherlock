#!/usr/bin/env python3
"""
Comprehensive VM Latency Analysis Script

Parses raw measurement logs and generates detailed analysis report with:
- Per-segment statistics (avg/min/max/stddev/samples)
- Layer attribution breakdown
- Data path visualization
- Validation checks
- Findings and recommendations

Usage:
    python analyze_measurement.py <measurement_dir> [--output report.json]
"""

import json
import math
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class SegmentStats:
    """Statistics for a single latency segment."""
    name: str
    avg_us: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    stddev_us: float = 0.0
    samples: int = 0
    source: str = ""
    description: str = ""

    @property
    def avg_ms(self) -> float:
        return self.avg_us / 1000.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "avg_us": round(self.avg_us, 3),
            "avg_ms": round(self.avg_ms, 6),
            "min_us": round(self.min_us, 3),
            "max_us": round(self.max_us, 3),
            "stddev_us": round(self.stddev_us, 3),
            "samples": self.samples,
            "source": self.source,
            "description": self.description,
        }


@dataclass
class LayerAttribution:
    """Attribution data for a network layer."""
    name: str
    total_us: float = 0.0
    percentage: float = 0.0
    segments: List[str] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return self.total_us / 1000.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_us": round(self.total_us, 3),
            "total_ms": round(self.total_ms, 6),
            "percentage": round(self.percentage, 2),
            "segments": self.segments,
        }


@dataclass
class RawMeasurement:
    """Raw measurement data from a single log file."""
    file_name: str
    values: Dict[str, List[float]] = field(default_factory=dict)

    def get_stats(self, key: str) -> SegmentStats:
        """Calculate statistics for a measurement key."""
        values = self.values.get(key, [])
        if not values:
            return SegmentStats(name=key)

        avg = sum(values) / len(values)
        min_val = min(values)
        max_val = max(values)

        # Calculate stddev
        if len(values) > 1:
            variance = sum((x - avg) ** 2 for x in values) / (len(values) - 1)
            stddev = math.sqrt(variance)
        else:
            stddev = 0.0

        return SegmentStats(
            name=key,
            avg_us=avg,
            min_us=min_val,
            max_us=max_val,
            stddev_us=stddev,
            samples=len(values),
        )


def parse_kernel_icmp_rtt_log(filepath: Path) -> RawMeasurement:
    """Parse kernel_icmp_rtt.py output."""
    result = RawMeasurement(
        file_name=filepath.name,
        values={
            "path1": [],
            "path2": [],
            "inter_path": [],
            "total_rtt": [],
        }
    )

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        for line in f:
            if "Total Path 1:" in line:
                match = re.search(r"Total Path 1:\s+([\d.]+)\s+us", line)
                if match:
                    result.values["path1"].append(float(match.group(1)))
            elif "Total Path 2:" in line:
                match = re.search(r"Total Path 2:\s+([\d.]+)\s+us", line)
                if match:
                    result.values["path2"].append(float(match.group(1)))
            elif "Inter-Path" in line:
                match = re.search(r"Inter-Path[^:]+:\s+([\d.]+)\s+us", line)
                if match:
                    result.values["inter_path"].append(float(match.group(1)))
            elif "Total RTT" in line:
                match = re.search(r"Total RTT[^:]+:\s+([\d.]+)\s+us", line)
                if match:
                    result.values["total_rtt"].append(float(match.group(1)))

    return result


def parse_icmp_drop_detector_log(filepath: Path) -> RawMeasurement:
    """Parse icmp_drop_detector.py output."""
    result = RawMeasurement(
        file_name=filepath.name,
        values={
            "req_internal": [],
            "external": [],
            "rep_internal": [],
            "total": [],
        }
    )

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        for line in f:
            if "Latency" in line and "ReqInternal=" in line:
                match = re.search(r"ReqInternal=([\d.]+)", line)
                if match:
                    result.values["req_internal"].append(float(match.group(1)))
                match = re.search(r"External=([\d.]+)", line)
                if match:
                    result.values["external"].append(float(match.group(1)))
                match = re.search(r"RepInternal=([\d.]+)", line)
                if match:
                    result.values["rep_internal"].append(float(match.group(1)))
                match = re.search(r"Total=([\d.]+)", line)
                if match:
                    result.values["total"].append(float(match.group(1)))

    return result


def parse_tun_tx_to_kvm_irq_log(filepath: Path) -> RawMeasurement:
    """Parse tun_tx_to_kvm_irq.py output (values in ms)."""
    result = RawMeasurement(
        file_name=filepath.name,
        values={
            "total_delay_ms": [],
            "s2_delay_ms": [],
            "s3_delay_ms": [],
            "s4_delay_ms": [],
            "s5_delay_ms": [],
        }
    )

    if not filepath.exists():
        return result

    # First try per-packet total lines
    with open(filepath, "r") as f:
        for line in f:
            if "-> Total(S1->S5):" in line:
                match = re.search(r"Total\(S1->S5\):\s+([\d.]+)ms", line)
                if match:
                    result.values["total_delay_ms"].append(float(match.group(1)))

    if result.values["total_delay_ms"]:
        return result

    # Fallback: calculate from per-stage delays
    stage_delays = {}
    current_chain = 0

    with open(filepath, "r") as f:
        for line in f:
            if "Stage 1 [tun_net_xmit]" in line:
                current_chain += 1
                stage_delays[current_chain] = {}
            elif current_chain > 0:
                for stage in [2, 3, 4, 5]:
                    if f"Stage {stage} [" in line:
                        match = re.search(r"Delay=([\d.]+)ms", line)
                        if match:
                            stage_delays[current_chain][stage] = float(match.group(1))

    for chain_id, stages in stage_delays.items():
        if 2 in stages and 3 in stages and 4 in stages and 5 in stages:
            total = stages[2] + stages[3] + stages[4] + stages[5]
            result.values["total_delay_ms"].append(total)

    return result


def parse_kvm_vhost_tun_latency_log(filepath: Path) -> RawMeasurement:
    """Parse kvm_vhost_tun_latency_details.py output."""
    result = RawMeasurement(
        file_name=filepath.name,
        values={
            "s0": [],
            "s1": [],
            "s2": [],
            "total": [],
        }
    )

    if not filepath.exists():
        return result

    with open(filepath, "r") as f:
        for line in f:
            # Parse per-packet lines: s0=14us s1=5us s2=4us total=23us
            if "total=" in line.lower() and "us" in line.lower():
                match = re.search(r"s0=([\d.]+)\s*us", line, re.IGNORECASE)
                if match:
                    result.values["s0"].append(float(match.group(1)))
                match = re.search(r"s1=([\d.]+)\s*us", line, re.IGNORECASE)
                if match:
                    result.values["s1"].append(float(match.group(1)))
                match = re.search(r"s2=([\d.]+)\s*us", line, re.IGNORECASE)
                if match:
                    result.values["s2"].append(float(match.group(1)))
                match = re.search(r"total=([\d.]+)\s*us", line, re.IGNORECASE)
                if match:
                    result.values["total"].append(float(match.group(1)))

    return result


def avg(values: List[float]) -> float:
    """Calculate average, return 0 if empty."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def analyze_measurements(measurement_dir: Path, breakdown: Optional[dict] = None) -> dict:
    """
    Analyze all measurement logs and generate comprehensive report.

    Args:
        measurement_dir: Directory containing 8 log files
        breakdown: Optional pre-calculated breakdown from controller

    Returns:
        Comprehensive analysis report dict
    """

    # Parse all 8 log files
    sender_vm = parse_kernel_icmp_rtt_log(measurement_dir / "send-vm-icmp.log")
    receiver_vm = parse_kernel_icmp_rtt_log(measurement_dir / "recv-vm-icmp.log")
    sender_host = parse_icmp_drop_detector_log(measurement_dir / "send-host-icmp.log")
    receiver_host = parse_icmp_drop_detector_log(measurement_dir / "recv-host-icmp.log")
    sender_vhost_rx = parse_tun_tx_to_kvm_irq_log(measurement_dir / "send-host-vhost-rx.log")
    receiver_vhost_rx = parse_tun_tx_to_kvm_irq_log(measurement_dir / "recv-host-vhost-rx.log")
    sender_kvm_tun = parse_kvm_vhost_tun_latency_log(measurement_dir / "send-host-kvm-tun.log")
    receiver_kvm_tun = parse_kvm_vhost_tun_latency_log(measurement_dir / "recv-host-kvm-tun.log")

    # Build segment statistics
    segments: Dict[str, SegmentStats] = {}

    # Segment A: Sender VM TX (Path 1)
    stats = sender_vm.get_stats("path1")
    stats.name = "A"
    stats.source = "send-vm-icmp.log (Path 1)"
    stats.description = "Sender VM kernel TX processing"
    segments["A"] = stats

    # Segment M: Sender VM RX (Path 2)
    stats = sender_vm.get_stats("path2")
    stats.name = "M"
    stats.source = "send-vm-icmp.log (Path 2)"
    stats.description = "Sender VM kernel RX processing"
    segments["M"] = stats

    # Segment F: Receiver VM RX (Path 1)
    stats = receiver_vm.get_stats("path1")
    stats.name = "F"
    stats.source = "recv-vm-icmp.log (Path 1)"
    stats.description = "Receiver VM kernel RX processing"
    segments["F"] = stats

    # Segment G: Receiver VM ICMP processing (Inter-Path)
    stats = receiver_vm.get_stats("inter_path")
    stats.name = "G"
    stats.source = "recv-vm-icmp.log (Inter-Path)"
    stats.description = "Receiver VM ICMP echo processing"
    segments["G"] = stats

    # Segment H: Receiver VM TX (Path 2)
    stats = receiver_vm.get_stats("path2")
    stats.name = "H"
    stats.source = "recv-vm-icmp.log (Path 2)"
    stats.description = "Receiver VM kernel TX processing"
    segments["H"] = stats

    # Segment B: Sender Host OVS forwarding (Request)
    stats = sender_host.get_stats("req_internal")
    stats.name = "B"
    stats.source = "send-host-icmp.log (ReqInternal)"
    stats.description = "Sender Host OVS request forwarding"
    segments["B"] = stats

    # Segment K: Sender Host OVS forwarding (Reply)
    stats = sender_host.get_stats("rep_internal")
    stats.name = "K"
    stats.source = "send-host-icmp.log (RepInternal)"
    stats.description = "Sender Host OVS reply forwarding"
    segments["K"] = stats

    # Segment D: Receiver Host OVS forwarding (Request)
    stats = receiver_host.get_stats("req_internal")
    stats.name = "D"
    stats.source = "recv-host-icmp.log (ReqInternal)"
    stats.description = "Receiver Host OVS request forwarding"
    segments["D"] = stats

    # Segment I: Receiver Host OVS forwarding (Reply)
    stats = receiver_host.get_stats("rep_internal")
    stats.name = "I"
    stats.source = "recv-host-icmp.log (RepInternal)"
    stats.description = "Receiver Host OVS reply forwarding"
    segments["I"] = stats

    # Segment E: Receiver Host vhost→KVM (TUN to KVM IRQ injection)
    vhost_stats = receiver_vhost_rx.get_stats("total_delay_ms")
    segments["E"] = SegmentStats(
        name="E",
        avg_us=vhost_stats.avg_us * 1000,  # ms to us
        min_us=vhost_stats.min_us * 1000,
        max_us=vhost_stats.max_us * 1000,
        stddev_us=vhost_stats.stddev_us * 1000,
        samples=vhost_stats.samples,
        source="recv-host-vhost-rx.log (Total S1→S5)",
        description="Receiver vhost→KVM IRQ injection",
    )

    # Segment L: Sender Host vhost→KVM (TUN to KVM IRQ injection)
    vhost_stats = sender_vhost_rx.get_stats("total_delay_ms")
    segments["L"] = SegmentStats(
        name="L",
        avg_us=vhost_stats.avg_us * 1000,  # ms to us
        min_us=vhost_stats.min_us * 1000,
        max_us=vhost_stats.max_us * 1000,
        stddev_us=vhost_stats.stddev_us * 1000,
        samples=vhost_stats.samples,
        source="send-host-vhost-rx.log (Total S1→S5)",
        description="Sender vhost→KVM IRQ injection",
    )

    # Segment B_1: Sender Host KVM→TUN (VM TX path)
    stats = sender_kvm_tun.get_stats("total")
    stats.name = "B_1"
    stats.source = "send-host-kvm-tun.log (Total S0+S1+S2)"
    stats.description = "Sender KVM→vhost→TUN transmission"
    segments["B_1"] = stats

    # Segment I_1: Receiver Host KVM→TUN (VM TX path)
    stats = receiver_kvm_tun.get_stats("total")
    stats.name = "I_1"
    stats.source = "recv-host-kvm-tun.log (Total S0+S1+S2)"
    stats.description = "Receiver KVM→vhost→TUN transmission"
    segments["I_1"] = stats

    # Calculate C_J (Physical Network) = Sender External - Receiver Host Total
    sender_external = avg(sender_host.values.get("external", []))
    receiver_host_total = avg(receiver_host.values.get("total", []))
    c_j_value = sender_external - receiver_host_total if receiver_host_total > 0 else 0

    segments["C_J"] = SegmentStats(
        name="C_J",
        avg_us=c_j_value,
        min_us=c_j_value,  # Derived, no variance
        max_us=c_j_value,
        stddev_us=0,
        samples=1,
        source="Derived: Sender External - Receiver Host Total",
        description="Physical network latency (request + reply)",
    )

    # Calculate total RTT
    total_rtt_stats = sender_vm.get_stats("total_rtt")
    total_rtt_us = total_rtt_stats.avg_us

    # If not available from logs, calculate from segments
    if total_rtt_us == 0:
        total_rtt_us = sum(seg.avg_us for seg in segments.values())

    # Calculate layer attribution
    layer_segments = {
        "vm_kernel": ["A", "F", "G", "H", "M"],
        "host_ovs": ["B", "D", "I", "K"],
        "physical_network": ["C_J"],
        "virt_rx": ["E", "L"],
        "virt_tx": ["B_1", "I_1"],
    }

    layer_descriptions = {
        "vm_kernel": "VM Internal Kernel Stack",
        "host_ovs": "Host OVS/Bridge Forwarding",
        "physical_network": "Physical Network (Wire/Switch)",
        "virt_rx": "Virtualization RX Path (TUN→KVM)",
        "virt_tx": "Virtualization TX Path (KVM→TUN)",
    }

    layers: Dict[str, LayerAttribution] = {}
    for layer_name, seg_names in layer_segments.items():
        total = sum(segments[s].avg_us for s in seg_names if s in segments)
        percentage = (total / total_rtt_us * 100) if total_rtt_us > 0 else 0
        layers[layer_name] = LayerAttribution(
            name=layer_descriptions[layer_name],
            total_us=total,
            percentage=percentage,
            segments=seg_names,
        )

    # Sort layers by percentage
    sorted_layers = sorted(layers.items(), key=lambda x: x[1].percentage, reverse=True)
    primary_contributor = sorted_layers[0][0] if sorted_layers else "unknown"

    # Validation: compare calculated vs measured total
    calculated_total = sum(seg.avg_us for seg in segments.values())
    validation_error_pct = abs(calculated_total - total_rtt_us) / total_rtt_us * 100 if total_rtt_us > 0 else 0

    # Generate findings
    findings = []

    # Finding 1: Total latency
    findings.append({
        "type": "total_latency",
        "title": "Total Round-Trip Latency",
        "value_us": round(total_rtt_us, 3),
        "value_ms": round(total_rtt_us / 1000, 6),
        "samples": total_rtt_stats.samples,
        "min_us": round(total_rtt_stats.min_us, 3),
        "max_us": round(total_rtt_stats.max_us, 3),
        "stddev_us": round(total_rtt_stats.stddev_us, 3),
    })

    # Finding 2: Primary bottleneck
    if sorted_layers:
        top_layer_name, top_layer = sorted_layers[0]
        findings.append({
            "type": "primary_bottleneck",
            "title": "Primary Latency Contributor",
            "layer": top_layer_name,
            "layer_name": top_layer.name,
            "latency_us": round(top_layer.total_us, 3),
            "percentage": round(top_layer.percentage, 2),
            "segments": top_layer.segments,
        })

    # Finding 3: Top 3 contributors
    findings.append({
        "type": "top_contributors",
        "title": "Layer Attribution Summary",
        "layers": [
            {
                "layer": name,
                "layer_name": layer.name,
                "latency_us": round(layer.total_us, 3),
                "percentage": round(layer.percentage, 2),
            }
            for name, layer in sorted_layers
        ],
    })

    # Finding 4: Highest variance segments
    high_variance_segments = sorted(
        [(name, seg) for name, seg in segments.items() if seg.samples > 1],
        key=lambda x: x[1].stddev_us,
        reverse=True
    )[:3]

    if high_variance_segments:
        findings.append({
            "type": "variance_analysis",
            "title": "Segments with Highest Variance",
            "segments": [
                {
                    "name": name,
                    "stddev_us": round(seg.stddev_us, 3),
                    "avg_us": round(seg.avg_us, 3),
                    "cv_pct": round(seg.stddev_us / seg.avg_us * 100, 2) if seg.avg_us > 0 else 0,
                }
                for name, seg in high_variance_segments
            ],
        })

    # Generate recommendations
    recommendations = []

    if primary_contributor == "host_ovs":
        recommendations.extend([
            {"priority": "high", "action": "Optimize OVS bridge configuration and flow rules", "rationale": "Host OVS is the primary latency contributor"},
            {"priority": "medium", "action": "Consider OVS-DPDK for high-performance forwarding", "rationale": "DPDK can significantly reduce OVS processing latency"},
            {"priority": "medium", "action": "Review OVS flow table for unnecessary complexity", "rationale": "Complex flow rules increase lookup latency"},
        ])
    elif primary_contributor == "vm_kernel":
        recommendations.extend([
            {"priority": "high", "action": "Optimize VM guest kernel network parameters", "rationale": "VM kernel stack is the primary latency contributor"},
            {"priority": "medium", "action": "Review virtio-net driver configuration", "rationale": "Driver settings affect packet processing efficiency"},
            {"priority": "medium", "action": "Consider CPU pinning for VM vCPUs", "rationale": "Reduces context switching overhead"},
        ])
    elif primary_contributor == "physical_network":
        recommendations.extend([
            {"priority": "high", "action": "Investigate physical switch latency", "rationale": "Physical network is the primary latency contributor"},
            {"priority": "medium", "action": "Verify NIC speed and duplex settings", "rationale": "Mismatched settings can cause delays"},
            {"priority": "medium", "action": "Check for packet loss on physical interfaces", "rationale": "Retransmissions add latency"},
        ])
    elif primary_contributor == "virt_rx":
        recommendations.extend([
            {"priority": "high", "action": "Optimize vhost-net thread scheduling", "rationale": "Virtualization RX path is the primary latency contributor"},
            {"priority": "medium", "action": "Review IRQ affinity for vhost threads", "rationale": "Proper IRQ affinity reduces processing latency"},
        ])
    elif primary_contributor == "virt_tx":
        recommendations.extend([
            {"priority": "high", "action": "Optimize KVM→vhost interface", "rationale": "Virtualization TX path is the primary latency contributor"},
            {"priority": "medium", "action": "Review TX queue depth configuration", "rationale": "Queue depth affects batching efficiency"},
        ])

    # General recommendations based on total latency
    if total_rtt_us > 1000:
        recommendations.append({
            "priority": "high",
            "action": "Total latency exceeds 1ms - comprehensive performance audit recommended",
            "rationale": f"Current RTT: {total_rtt_us:.0f}us exceeds acceptable threshold",
        })
    elif total_rtt_us > 500:
        recommendations.append({
            "priority": "medium",
            "action": "Monitor latency trends for potential degradation",
            "rationale": f"Current RTT: {total_rtt_us:.0f}us is moderate",
        })

    # Build raw measurement summary
    raw_measurements = {
        "sender_vm": {
            "file": "send-vm-icmp.log",
            "path1": sender_vm.get_stats("path1").to_dict(),
            "path2": sender_vm.get_stats("path2").to_dict(),
            "inter_path": sender_vm.get_stats("inter_path").to_dict(),
            "total_rtt": sender_vm.get_stats("total_rtt").to_dict(),
        },
        "receiver_vm": {
            "file": "recv-vm-icmp.log",
            "path1": receiver_vm.get_stats("path1").to_dict(),
            "path2": receiver_vm.get_stats("path2").to_dict(),
            "inter_path": receiver_vm.get_stats("inter_path").to_dict(),
        },
        "sender_host": {
            "file": "send-host-icmp.log",
            "req_internal": sender_host.get_stats("req_internal").to_dict(),
            "external": sender_host.get_stats("external").to_dict(),
            "rep_internal": sender_host.get_stats("rep_internal").to_dict(),
            "total": sender_host.get_stats("total").to_dict(),
        },
        "receiver_host": {
            "file": "recv-host-icmp.log",
            "req_internal": receiver_host.get_stats("req_internal").to_dict(),
            "external": receiver_host.get_stats("external").to_dict(),
            "rep_internal": receiver_host.get_stats("rep_internal").to_dict(),
            "total": receiver_host.get_stats("total").to_dict(),
        },
        "sender_vhost_rx": {
            "file": "send-host-vhost-rx.log",
            "total_delay_ms": sender_vhost_rx.get_stats("total_delay_ms").to_dict(),
        },
        "receiver_vhost_rx": {
            "file": "recv-host-vhost-rx.log",
            "total_delay_ms": receiver_vhost_rx.get_stats("total_delay_ms").to_dict(),
        },
        "sender_kvm_tun": {
            "file": "send-host-kvm-tun.log",
            "s0": sender_kvm_tun.get_stats("s0").to_dict(),
            "s1": sender_kvm_tun.get_stats("s1").to_dict(),
            "s2": sender_kvm_tun.get_stats("s2").to_dict(),
            "total": sender_kvm_tun.get_stats("total").to_dict(),
        },
        "receiver_kvm_tun": {
            "file": "recv-host-kvm-tun.log",
            "s0": receiver_kvm_tun.get_stats("s0").to_dict(),
            "s1": receiver_kvm_tun.get_stats("s1").to_dict(),
            "s2": receiver_kvm_tun.get_stats("s2").to_dict(),
            "total": receiver_kvm_tun.get_stats("total").to_dict(),
        },
    }

    # Build comprehensive report
    report = {
        "analysis_type": "VM Cross-Node ICMP Latency Analysis",
        "measurement_dir": str(measurement_dir),
        "timestamp": datetime.now().isoformat(),

        "summary": {
            "total_rtt_us": round(total_rtt_us, 3),
            "total_rtt_ms": round(total_rtt_us / 1000, 6),
            "primary_contributor": primary_contributor,
            "primary_contributor_name": layers[primary_contributor].name if primary_contributor in layers else "Unknown",
            "primary_contributor_pct": round(layers[primary_contributor].percentage, 2) if primary_contributor in layers else 0,
            "validation_error_pct": round(validation_error_pct, 2),
            "sample_count": total_rtt_stats.samples,
        },

        "segments": {
            name: seg.to_dict() for name, seg in segments.items()
        },

        "layer_attribution": {
            name: layer.to_dict() for name, layer in layers.items()
        },

        "layer_attribution_sorted": [
            {"layer": name, **layer.to_dict()}
            for name, layer in sorted_layers
        ],

        "validation": {
            "measured_total_us": round(total_rtt_us, 3),
            "calculated_total_us": round(calculated_total, 3),
            "difference_us": round(abs(calculated_total - total_rtt_us), 3),
            "error_pct": round(validation_error_pct, 2),
            "status": "Valid" if validation_error_pct <= 5 else "Warning" if validation_error_pct <= 10 else "Error",
        },

        "findings": findings,
        "recommendations": recommendations,

        "raw_measurements": raw_measurements,

        "data_path_diagram": generate_data_path_diagram(segments),
    }

    return report


def generate_data_path_diagram(segments: Dict[str, SegmentStats]) -> str:
    """Generate ASCII data path diagram with latency values."""

    def fmt(name: str) -> str:
        if name in segments:
            return f"{name}={segments[name].avg_us:.1f}us"
        return f"{name}=?"

    diagram = f"""
ICMP Request Path (Sender → Receiver):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Sender VM     │    │   Sender Host   │    │   Network   │    │  Receiver Host  │    │  Receiver VM    │
│                 │    │                 │    │             │    │                 │    │                 │
│ [A] TX Kernel   │───▶│ [B] OVS Fwd     │───▶│ [C] Wire    │───▶│ [D] OVS Fwd     │───▶│ [F] RX Kernel   │
│ {fmt('A'):^15s} │    │ {fmt('B'):^15s} │    │             │    │ {fmt('D'):^15s} │    │ {fmt('F'):^15s} │
│                 │    │ [B_1] KVM→TUN   │    │             │    │ [E] TUN→KVM     │    │ [G] ICMP Proc   │
│                 │    │ {fmt('B_1'):^15s} │    │             │    │ {fmt('E'):^15s} │    │ {fmt('G'):^15s} │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

ICMP Reply Path (Receiver → Sender):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Receiver VM    │    │  Receiver Host  │    │   Network   │    │   Sender Host   │    │   Sender VM     │
│                 │    │                 │    │             │    │                 │    │                 │
│ [H] TX Kernel   │───▶│ [I] OVS Fwd     │───▶│ [J] Wire    │───▶│ [K] OVS Fwd     │───▶│ [M] RX Kernel   │
│ {fmt('H'):^15s} │    │ {fmt('I'):^15s} │    │             │    │ {fmt('K'):^15s} │    │ {fmt('M'):^15s} │
│                 │    │ [I_1] KVM→TUN   │    │             │    │ [L] TUN→KVM     │    │                 │
│                 │    │ {fmt('I_1'):^15s} │    │             │    │ {fmt('L'):^15s} │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

Physical Network (C+J): {fmt('C_J')}
"""
    return diagram


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_measurement.py <measurement_dir> [--output report.json]", file=sys.stderr)
        sys.exit(1)

    measurement_dir = Path(sys.argv[1])

    if not measurement_dir.exists():
        print(f"Error: Directory not found: {measurement_dir}", file=sys.stderr)
        sys.exit(1)

    output_file = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    report = analyze_measurements(measurement_dir)

    # Output JSON
    json_output = json.dumps(report, indent=2)

    if output_file:
        with open(output_file, "w") as f:
            f.write(json_output)
        print(f"Report written to: {output_file}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()
