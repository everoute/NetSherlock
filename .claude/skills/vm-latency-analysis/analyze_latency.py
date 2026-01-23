#!/usr/bin/env python3
"""
VM Latency Analysis Script

Analyzes cross-node VM ICMP ping latency by processing measurement breakdown data
and generating attribution analysis.
"""

import json
import sys
from typing import Dict, List, Any
from dataclasses import dataclass, asdict


@dataclass
class SegmentInfo:
    value_us: float
    value_ms: float
    source: str = ""
    description: str = ""


@dataclass
class LayerAttribution:
    total_us: float
    total_ms: float
    percentage: float
    segments: List[str]


def analyze_latency(breakdown: Dict[str, Any], environment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze latency breakdown and generate comprehensive report.

    Args:
        breakdown: Latency breakdown data with segments and layer attribution
        environment: Environment information (src/dst hosts, IPs, etc.)

    Returns:
        Comprehensive analysis report
    """

    # Extract data
    total_rtt_us = breakdown.get('total_rtt_us', 0)
    total_rtt_ms = breakdown.get('total_rtt_ms', 0)
    segments = breakdown.get('segments', {})
    layer_attribution = breakdown.get('layer_attribution', {})
    validation_error_pct = breakdown.get('validation_error_pct', 0)
    primary_contributor = breakdown.get('primary_contributor', '')

    # Build segment summary
    segment_summary = {}
    for seg_name, seg_data in segments.items():
        segment_summary[seg_name] = {
            'value_us': seg_data.get('value_us', 0),
            'value_ms': seg_data.get('value_ms', 0),
            'source': seg_data.get('source', ''),
            'description': seg_data.get('description', '')
        }

    # Build layer attribution summary
    layer_summary = {}
    for layer_name, layer_data in layer_attribution.items():
        layer_summary[layer_name] = {
            'total_us': layer_data.get('total_us', 0),
            'total_ms': layer_data.get('total_ms', 0),
            'percentage': layer_data.get('percentage', 0),
            'segments': layer_data.get('segments', [])
        }

    # Sort layers by percentage (descending)
    sorted_layers = sorted(
        layer_summary.items(),
        key=lambda x: x[1]['percentage'],
        reverse=True
    )

    # Generate findings
    findings = generate_findings(
        total_rtt_us, total_rtt_ms, sorted_layers,
        validation_error_pct, primary_contributor
    )

    # Build comprehensive report
    report = {
        'analysis_type': 'VM Cross-Node ICMP Latency Analysis',
        'environment': {
            'source': {
                'host': environment.get('src_host', ''),
                'test_ip': environment.get('src_test_ip', ''),
                'env': environment.get('src_env', {})
            },
            'destination': {
                'host': environment.get('dst_host', ''),
                'test_ip': environment.get('dst_test_ip', ''),
                'env': environment.get('dst_env', {})
            },
            'network_type': environment.get('network_type', '')
        },
        'total_latency': {
            'total_rtt_us': total_rtt_us,
            'total_rtt_ms': total_rtt_ms
        },
        'segments': segment_summary,
        'layer_attribution': {
            layer_name: layer_data
            for layer_name, layer_data in sorted_layers
        },
        'validation': {
            'error_percentage': validation_error_pct,
            'status': 'Valid' if validation_error_pct <= 5 else 'Warning'
        },
        'primary_contributor': primary_contributor,
        'findings': findings,
        'recommendations': generate_recommendations(
            sorted_layers, primary_contributor, total_rtt_us
        )
    }

    return report


def generate_findings(
    total_rtt_us: float,
    total_rtt_ms: float,
    sorted_layers: List[tuple],
    validation_error_pct: float,
    primary_contributor: str
) -> List[Dict[str, str]]:
    """Generate key findings from the analysis."""

    findings = []

    # Total latency finding
    findings.append({
        'type': 'Total Latency',
        'value': f'{total_rtt_ms:.4f} ms ({total_rtt_us:.3f} µs)',
        'description': f'End-to-end round-trip latency'
    })

    # Primary contributor finding
    if sorted_layers:
        top_layer, top_data = sorted_layers[0]
        findings.append({
            'type': 'Primary Bottleneck',
            'layer': top_layer,
            'percentage': f"{top_data['percentage']:.2f}%",
            'latency_ms': f"{top_data['total_ms']:.4f}",
            'description': f'{top_layer.replace("_", " ").title()} accounts for {top_data["percentage"]:.2f}% of total latency'
        })

    # Layer breakdown finding
    if len(sorted_layers) > 1:
        top_3 = sorted_layers[:3]
        findings.append({
            'type': 'Top Contributors',
            'layers': [
                {
                    'name': name,
                    'percentage': f"{data['percentage']:.2f}%",
                    'latency_ms': f"{data['total_ms']:.4f}"
                }
                for name, data in top_3
            ]
        })

    # Validation finding
    if validation_error_pct > 5:
        findings.append({
            'type': 'Validation Warning',
            'error_pct': f"{validation_error_pct:.2f}%",
            'severity': 'High' if validation_error_pct > 10 else 'Medium',
            'description': 'Validation error indicates potential measurement inconsistencies'
        })

    return findings


def generate_recommendations(
    sorted_layers: List[tuple],
    primary_contributor: str,
    total_rtt_us: float
) -> List[str]:
    """Generate optimization recommendations."""

    recommendations = []

    if sorted_layers:
        top_layer, top_data = sorted_layers[0]

        # Layer-specific recommendations
        if top_layer == 'host_ovs':
            recommendations.extend([
                'Optimize OVS bridge configuration and forwarding rules',
                'Consider using OVS Hardware Offload if available',
                'Review OVS DPDK integration for high-performance scenarios',
                'Check for excessive OVS CPU usage or contention'
            ])
        elif top_layer == 'physical_network':
            recommendations.extend([
                'Investigate physical switch latency and queue depths',
                'Verify network interface speed and duplex settings',
                'Check for packet loss or retransmissions on physical network',
                'Consider network optimization or upgrade if consistent high latency'
            ])
        elif top_layer == 'vm_kernel':
            recommendations.extend([
                'Profile VM kernel network stack for bottlenecks',
                'Optimize VM guest OS network parameters (buffer sizes, interrupt coalescing)',
                'Consider CPU pinning and NUMA optimizations for VMs',
                'Review guest kernel driver versions for virtio-net'
            ])
        elif top_layer == 'virt_rx':
            recommendations.extend([
                'Optimize vhost-net thread CPU pinning and isolation',
                'Review TUN→KVM IRQ injection latency',
                'Check for vhost queue depth and buffer configurations',
                'Consider vhost DPDK integration for RX path optimization'
            ])
        elif top_layer == 'virt_tx':
            recommendations.extend([
                'Optimize KVM→vhost interface latency',
                'Review TX buffer configurations and queue sizes',
                'Consider TSO/GSO optimization for TX path',
                'Check vhost thread scheduling and CPU allocation'
            ])

    # General recommendations
    if total_rtt_us > 1000:  # > 1ms
        recommendations.append('Total latency exceeds 1ms - consider performance tuning')
    elif total_rtt_us > 500:  # > 0.5ms
        recommendations.append('Moderate latency detected - monitor for impact on applications')

    return recommendations


def main():
    """Main entry point for latency analysis."""

    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("VM Latency Analysis - Analyze cross-node VM ICMP latency")
        print("\nUsage: python analyze_latency.py <breakdown_json> <environment_json>")
        sys.exit(0)

    # For direct execution with embedded data
    breakdown_data = {
        'total_rtt_us': 705.181,
        'total_rtt_ms': 0.7051810000000001,
        'segments': {
            'A': {'value_us': 51.062, 'value_ms': 0.051061999999999996, 'source': '', 'description': ''},
            'B': {'value_us': 54.342, 'value_ms': 0.054342, 'source': '', 'description': ''},
            'B_1': {'value_us': 0.0, 'value_ms': 0.0, 'source': '', 'description': ''},
            'C_J': {'value_us': 33.943, 'value_ms': 0.033943, 'source': '', 'description': ''},
            'D': {'value_us': 98.903, 'value_ms': 0.098903, 'source': '', 'description': ''},
            'E': {'value_us': 90.098, 'value_ms': 0.090098, 'source': '', 'description': ''},
            'F': {'value_us': 48.808, 'value_ms': 0.048808, 'source': '', 'description': ''},
            'G': {'value_us': 17.187, 'value_ms': 0.017187, 'source': '', 'description': ''},
            'H': {'value_us': 39.709, 'value_ms': 0.039709, 'source': '', 'description': ''},
            'I': {'value_us': 66.181, 'value_ms': 0.066181, 'source': '', 'description': ''},
            'I_1': {'value_us': 0.0, 'value_ms': 0.0, 'source': '', 'description': ''},
            'K': {'value_us': 64.454, 'value_ms': 0.064454, 'source': '', 'description': ''},
            'L': {'value_us': 56.098, 'value_ms': 0.056098, 'source': '', 'description': ''},
            'M': {'value_us': 34.51, 'value_ms': 0.03451, 'source': '', 'description': ''}
        },
        'layer_attribution': {
            'vm_kernel': {
                'total_us': 191.276,
                'total_ms': 0.191276,
                'percentage': 27.124383668873662,
                'segments': ['A', 'F', 'G', 'H', 'M']
            },
            'host_ovs': {
                'total_us': 283.88,
                'total_ms': 0.28388,
                'percentage': 40.25633135322704,
                'segments': ['B', 'D', 'I', 'K']
            },
            'physical_network': {
                'total_us': 33.943,
                'total_ms': 0.033943,
                'percentage': 4.813374155004175,
                'segments': ['C_J']
            },
            'virt_rx': {
                'total_us': 146.196,
                'total_ms': 0.146196,
                'percentage': 20.731698670270468,
                'segments': ['E', 'L']
            },
            'virt_tx': {
                'total_us': 0.0,
                'total_ms': 0.0,
                'percentage': 0.0,
                'segments': ['B_1', 'I_1']
            }
        },
        'validation_error_pct': 0.0,
        'primary_contributor': 'host_ovs'
    }

    environment_data = {
        'src_host': '192.168.70.32',
        'dst_host': '192.168.70.31',
        'network_type': 'vm',
        'src_test_ip': '192.168.77.83',
        'dst_test_ip': '192.168.76.244',
        'src_env': {
            'pid': 18742,
            'name': 'vhost-18627'
        },
        'dst_env': {
            'pid': 18742,
            'name': 'vhost-18627',
            'vm_uuid': 'a8366b2a-a709-4e88-ba57-128681bd1efb',
            'vm_name': 'a8366b2a-a709-4e88-ba57-128681bd1efb',
            'qemu_pid': 43272
        }
    }

    # Run analysis
    report = analyze_latency(breakdown_data, environment_data)

    # Output as JSON
    print(json.dumps(report, indent=2))

    return 0


if __name__ == '__main__':
    sys.exit(main())
