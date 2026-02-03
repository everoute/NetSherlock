#!/usr/bin/env python3
"""Parse icmp_path_tracer.py verbose output (VM boundary tool).

Output format:
  [complete] ID=5465 Seq=1 ReqRX:Y ReqTX:Y RepRX:Y RepTX:Y
    Latency(us): ReqInternal=45.2  External=338.5  RepInternal=12.8  Total=396.5

Statistics format:
  === ICMP Flow Statistics ===
  Total flows tracked: N
  Complete flows: N
  Request internal drops: N
  External drops: N
  Reply internal drops: N
"""

import re
from typing import Dict, List, Optional


def parse_latency_values(content: str) -> Dict[str, List[float]]:
    """Parse all latency values from verbose output.

    Returns dict with lists of values for each segment.
    """
    # VM boundary ICMP: ReqInternal, External, RepInternal, Total
    latency_re = re.compile(
        r'Latency\(us\):\s+ReqInternal=([\d.]+)\s+External=([\d.]+)\s+RepInternal=([\d.]+)\s+Total=([\d.]+)'
    )
    segment_names = ['req_internal', 'external', 'rep_internal', 'total']

    latencies = {name: [] for name in segment_names}

    for match in latency_re.finditer(content):
        for i, name in enumerate(segment_names):
            latencies[name].append(float(match.group(i + 1)))

    return latencies


def calculate_stats(values: List[float]) -> Dict[str, float]:
    """Calculate statistics for a list of values."""
    if not values:
        return {'avg': 0.0, 'min': 0.0, 'max': 0.0, 'count': 0}

    return {
        'avg': round(sum(values) / len(values), 1),
        'min': round(min(values), 1),
        'max': round(max(values), 1),
        'count': len(values)
    }


def parse_statistics_block(content: str) -> Dict[str, int]:
    """Parse the statistics summary block at the end of output."""
    stats = {
        'total_flows': 0,
        'complete_flows': 0,
        'req_internal_drops': 0,
        'external_drops': 0,
        'rep_internal_drops': 0
    }

    # Total flows tracked
    match = re.search(r'Total flows tracked:\s*(\d+)', content)
    if match:
        stats['total_flows'] = int(match.group(1))

    # Complete flows
    match = re.search(r'Complete flows:\s*(\d+)', content)
    if match:
        stats['complete_flows'] = int(match.group(1))

    # Request internal drops
    match = re.search(r'Request internal drops:\s*(\d+)', content)
    if match:
        stats['req_internal_drops'] = int(match.group(1))

    # External drops
    match = re.search(r'External drops:\s*(\d+)', content)
    if match:
        stats['external_drops'] = int(match.group(1))

    # Reply internal drops
    match = re.search(r'Reply internal drops:\s*(\d+)', content)
    if match:
        stats['rep_internal_drops'] = int(match.group(1))

    return stats


def parse_icmp_verbose_log(content: str) -> dict:
    """Parse ICMP verbose log content from VM boundary tool.

    Args:
        content: Raw log file content

    Returns:
        Parsed data structure with flows, drops, and latency statistics.
    """
    # Parse all latency values
    latencies = parse_latency_values(content)

    # Parse statistics block
    stats = parse_statistics_block(content)

    # Build latency stats for each segment
    latency_stats = {}
    for segment_name, values in latencies.items():
        latency_stats[segment_name] = calculate_stats(values)

    # Segment display names for VM boundary
    segment_names = {
        'segment1': 'ReqInternal',
        'segment2': 'External',
        'segment3': 'RepInternal'
    }

    # Build drop names
    drop_names = {
        'req_internal': stats['req_internal_drops'],
        'external': stats['external_drops'],
        'rep_internal': stats['rep_internal_drops']
    }

    # Build output structure
    total_drops = sum(drop_names.values())
    total = stats['total_flows'] if stats['total_flows'] > 0 else 1  # Avoid div by zero

    result = {
        'flows': {
            'total': stats['total_flows'],
            'complete': stats['complete_flows'],
            'in_progress': stats['total_flows'] - stats['complete_flows'] - total_drops
        },
        'drops': drop_names,
        'drop_rate': round(total_drops / total, 4) if total > 0 else 0.0,
        'latency_us': {}
    }

    # Add latency stats with display names
    key_map = {
        'ReqInternal': 'req_internal',
        'External': 'external',
        'RepInternal': 'rep_internal'
    }

    for segment_key, display_name in segment_names.items():
        internal_key = key_map.get(display_name, display_name.lower())
        if internal_key in latency_stats:
            result['latency_us'][segment_key] = {
                'name': display_name,
                **latency_stats[internal_key]
            }

    # Add total latency
    if 'total' in latency_stats:
        result['latency_us']['total'] = latency_stats['total']

    return result


def parse_file(file_path: str) -> dict:
    """Parse a log file."""
    with open(file_path) as f:
        content = f.read()
    return parse_icmp_verbose_log(content)


if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: parse_icmp_verbose.py <log_file>", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    result = parse_file(file_path)
    print(json.dumps(result, indent=2))
