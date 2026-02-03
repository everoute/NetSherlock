#!/usr/bin/env python3
"""Parse system_icmp_path_tracer.py verbose output.

Handles both RX (local responds) and TX (local initiates) modes.

RX mode latency format:
  Latency(us): ReqPath=55.9 Stack=19.2 RepPath=50.3 Total=125.4

TX mode latency format:
  Latency(us): ReqPath=52.7 External=129.2 RepPath=68.4 Total=250.3

Statistics format:
  === ICMP System Path Statistics (RX mode) ===
  Total flows tracked: N
  Complete flows: N
  Request internal drops: N
  Stack no-reply: N  (RX mode) / External drops: N (TX mode)
  Reply internal drops: N
"""

import re
from typing import Dict, List, Optional, Tuple


def detect_direction(content: str) -> str:
    """Detect ICMP direction from log content."""
    if 'Direction: TX' in content:
        return 'tx'
    return 'rx'  # Default to RX


def parse_latency_values(content: str, direction: str) -> Dict[str, List[float]]:
    """Parse all latency values from verbose output.

    Returns dict with lists of values for each segment.
    """
    if direction == 'rx':
        # RX: ReqPath, Stack, RepPath, Total
        latency_re = re.compile(
            r'Latency\(us\):\s+ReqPath=([\d.]+)\s+Stack=([\d.]+)\s+RepPath=([\d.]+)\s+Total=([\d.]+)'
        )
        segment_names = ['req_path', 'stack', 'rep_path', 'total']
    else:
        # TX: ReqPath, External, RepPath, Total
        latency_re = re.compile(
            r'Latency\(us\):\s+ReqPath=([\d.]+)\s+External=([\d.]+)\s+RepPath=([\d.]+)\s+Total=([\d.]+)'
        )
        segment_names = ['req_path', 'external', 'rep_path', 'total']

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


def parse_statistics_block(content: str, direction: str) -> Dict[str, int]:
    """Parse the statistics summary block at the end of output."""
    stats = {
        'total_flows': 0,
        'complete_flows': 0,
        'req_internal_drops': 0,
        'stack_or_external_drops': 0,  # Stack no-reply (RX) or External (TX)
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

    # Stack no-reply (RX) or External drops (TX)
    if direction == 'rx':
        match = re.search(r'Stack no-reply:\s*(\d+)', content)
    else:
        match = re.search(r'External drops:\s*(\d+)', content)
    if match:
        stats['stack_or_external_drops'] = int(match.group(1))

    # Reply internal drops
    match = re.search(r'Reply internal drops:\s*(\d+)', content)
    if match:
        stats['rep_internal_drops'] = int(match.group(1))

    return stats


def parse_icmp_verbose_log(content: str, direction: Optional[str] = None) -> dict:
    """Parse ICMP verbose log content.

    Args:
        content: Raw log file content
        direction: 'rx' or 'tx'. If None, auto-detect from content.

    Returns:
        Parsed data structure with flows, drops, and latency statistics.
    """
    if direction is None:
        direction = detect_direction(content)

    # Parse all latency values
    latencies = parse_latency_values(content, direction)

    # Parse statistics block
    stats = parse_statistics_block(content, direction)

    # Build latency stats for each segment
    latency_stats = {}
    for segment_name, values in latencies.items():
        latency_stats[segment_name] = calculate_stats(values)

    # Determine segment display names based on direction
    if direction == 'rx':
        segment_names = {
            'segment1': 'ReqPath',
            'segment2': 'Stack',
            'segment3': 'RepPath'
        }
        drop_names = {
            'internal_request': stats['req_internal_drops'],
            'stack_no_reply': stats['stack_or_external_drops'],
            'internal_reply': stats['rep_internal_drops']
        }
    else:
        segment_names = {
            'segment1': 'ReqPath',
            'segment2': 'External',
            'segment3': 'RepPath'
        }
        drop_names = {
            'internal_request': stats['req_internal_drops'],
            'external': stats['stack_or_external_drops'],
            'internal_reply': stats['rep_internal_drops']
        }

    # Build output structure
    total_drops = sum(drop_names.values())
    total = stats['total_flows'] if stats['total_flows'] > 0 else 1  # Avoid div by zero

    result = {
        'direction': direction,
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
    for segment_key, display_name in segment_names.items():
        internal_key = display_name.lower().replace('_', '')
        if direction == 'rx':
            key_map = {'reqpath': 'req_path', 'stack': 'stack', 'reppath': 'rep_path'}
        else:
            key_map = {'reqpath': 'req_path', 'external': 'external', 'reppath': 'rep_path'}

        internal_key = key_map.get(internal_key, internal_key)
        if internal_key in latency_stats:
            result['latency_us'][segment_key] = {
                'name': display_name,
                **latency_stats[internal_key]
            }

    # Add total latency
    if 'total' in latency_stats:
        result['latency_us']['total'] = latency_stats['total']

    return result


def parse_file(file_path: str, direction: Optional[str] = None) -> dict:
    """Parse a log file."""
    with open(file_path) as f:
        content = f.read()
    return parse_icmp_verbose_log(content, direction)


if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: parse_icmp_verbose.py <log_file> [rx|tx]", file=sys.stderr)
        sys.exit(1)

    file_path = sys.argv[1]
    direction = sys.argv[2] if len(sys.argv) > 2 else None

    result = parse_file(file_path, direction)
    print(json.dumps(result, indent=2))
