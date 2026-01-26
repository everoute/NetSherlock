#!/usr/bin/env python3
"""
Parse kernel_drop_stack_stats_summary_all.py output into structured JSON.

Usage:
    python3 parse_stack_output.py < output.log
    python3 parse_stack_output.py output.log
    cat output.log | python3 parse_stack_output.py

Output: JSON with extracted stack trace entries
"""

import sys
import re
import json
from typing import List, Dict, Optional


def parse_stack_output(text: str) -> Dict:
    """Parse tool output into structured data."""
    entries = []
    current_entry = None
    in_stack_trace = False

    lines = text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # Match entry header: #1 Count: 81 calls [device: port-mgt] [stack_id: 617]
        entry_match = re.match(
            r'\s*#(\d+)\s+Count:\s*(\d+)\s+calls\s+\[device:\s*([^\]]+)\]\s+\[stack_id:\s*(\d+)\]',
            line
        )

        if entry_match:
            # Save previous entry if exists
            if current_entry:
                entries.append(current_entry)

            current_entry = {
                'rank': int(entry_match.group(1)),
                'count': int(entry_match.group(2)),
                'device': entry_match.group(3).strip(),
                'stack_id': int(entry_match.group(4)),
                'flow': None,
                'frames': [],
                'raw_frames': []
            }
            in_stack_trace = False
            i += 1
            continue

        # Match flow: Flow: 192.168.70.31 -> 192.168.70.32 (ICMP)
        flow_match = re.match(r'\s*Flow:\s*(.+)', line)
        if flow_match and current_entry:
            current_entry['flow'] = flow_match.group(1).strip()
            i += 1
            continue

        # Match stack trace header
        if re.match(r'\s*Stack trace:', line):
            in_stack_trace = True
            i += 1
            continue

        # Match stack depth
        depth_match = re.match(r'\s*Stack depth:\s*(\d+)\s+frames', line)
        if depth_match and current_entry:
            current_entry['stack_depth'] = int(depth_match.group(1))
            i += 1
            continue

        # Match stack frame: kfree_skb+0x1 [kernel] or icmp_rcv+0x177 [kernel]
        frame_match = re.match(r'\s*([a-zA-Z_][a-zA-Z0-9_\.]*)\+0x([0-9a-fA-F]+)\s+\[([^\]]+)\]', line)
        if frame_match and current_entry and in_stack_trace:
            frame = {
                'symbol': frame_match.group(1),
                'offset': '0x' + frame_match.group(2),
                'module': frame_match.group(3)
            }
            current_entry['frames'].append(frame)
            current_entry['raw_frames'].append(line.strip())
            i += 1
            continue

        # Match "... (N more frames)"
        more_match = re.match(r'\s*\.\.\.\s*\((\d+)\s+more frames\)', line)
        if more_match and current_entry:
            current_entry['hidden_frames'] = int(more_match.group(1))
            in_stack_trace = False
            i += 1
            continue

        # Separator or empty line ends stack trace
        if line.startswith('---') or line.startswith('===') or not line.strip():
            in_stack_trace = False

        i += 1

    # Don't forget the last entry
    if current_entry:
        entries.append(current_entry)

    # Extract metadata from the output
    metadata = extract_metadata(text)

    return {
        'metadata': metadata,
        'entries': entries,
        'unique_stacks': len(set(e['stack_id'] for e in entries)),
        'total_count': sum(e['count'] for e in entries)
    }


def extract_metadata(text: str) -> Dict:
    """Extract metadata from the output header."""
    metadata = {}

    # Match timestamp and cycle info
    cycle_match = re.search(
        r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+Cycle\s+(\d+)\s+-\s+Interval drops:\s+(\d+)',
        text
    )
    if cycle_match:
        metadata['timestamp'] = cycle_match.group(1)
        metadata['cycle'] = int(cycle_match.group(2))
        metadata['interval_drops'] = int(cycle_match.group(3))

    # Match grouping mode
    group_match = re.search(r'grouped by:\s*(\w+)', text)
    if group_match:
        metadata['group_by'] = group_match.group(1)

    # Match stack trace failures
    failure_matches = re.findall(r'(\S+):\s+(\d+)\s+failed', text)
    if failure_matches:
        metadata['stack_failures'] = {dev: int(count) for dev, count in failure_matches}

    return metadata


def dedupe_by_stack_id(entries: List[Dict]) -> List[Dict]:
    """Deduplicate entries by stack_id, keeping the one with highest count."""
    seen = {}
    for entry in entries:
        stack_id = entry['stack_id']
        if stack_id not in seen or entry['count'] > seen[stack_id]['count']:
            seen[stack_id] = entry
    return list(seen.values())


def get_kfree_caller(entry: Dict) -> Optional[Dict]:
    """Get the function that called kfree_skb (first frame after kfree_skb)."""
    frames = entry.get('frames', [])
    for i, frame in enumerate(frames):
        if frame['symbol'] == 'kfree_skb' and i + 1 < len(frames):
            return frames[i + 1]
    # If kfree_skb is not the first frame, return the first frame
    if frames and frames[0]['symbol'] != 'kfree_skb':
        return frames[0]
    return frames[1] if len(frames) > 1 else None


def main():
    # Read input from file or stdin
    if len(sys.argv) > 1 and sys.argv[1] != '-':
        with open(sys.argv[1], 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    result = parse_stack_output(text)

    # Add caller info for each entry
    for entry in result['entries']:
        caller = get_kfree_caller(entry)
        if caller:
            entry['kfree_caller'] = caller

    # Deduplicated view
    result['unique_entries'] = dedupe_by_stack_id(result['entries'])

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
