#!/usr/bin/env python3
"""
Analyze kernel stack traces from kfree_skb tracing tools.

This script:
1. Parses tool output to extract stack traces
2. Resolves addresses to source lines (via SSH to target host)
3. Analyzes source context to classify as drop or normal processing

Usage:
    python3 analyze_stacks.py --input output.log --target smartx@192.168.70.31
    python3 analyze_stacks.py --input output.log --target smartx@192.168.70.31 --kernel-source ../kernel

Output: Classification report for each unique stack trace
"""

import argparse
import json
import subprocess
import sys
import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import the parser
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from parse_stack_output import parse_stack_output, get_kfree_caller


# Drop context indicators
DROP_LABELS = {'drop', 'discard_it', 'error', 'csum_error', 'bad', 'fail', 'reject', 'invalid'}
NORMAL_LABELS = {'out', 'done', 'success', 'free', 'cleanup', 'exit'}
DROP_RETURNS = {'NET_RX_DROP', '-EINVAL', '-ENOMEM', '-ENOBUFS', '-ENOENT', '-EPERM'}
DROP_STATS = {'_MIB_INERRORS', '_MIB_CSUMERRORS', '_MIB_INDISCARDS'}


def run_remote_command(target_host: str, command: str, timeout: int = 30) -> Tuple[str, int]:
    """Run command on remote host via SSH."""
    ssh_cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', target_host, command]
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "ERROR: SSH command timed out", 1
    except Exception as e:
        return f"ERROR: {e}", 1


def resolve_symbol_remote(target_host: str, symbol: str, offset: str, module: str,
                          method: str = 'gdb') -> Optional[Dict]:
    """Resolve symbol+offset to source line on remote host."""
    kver_cmd = "uname -r"
    kver_out, _ = run_remote_command(target_host, kver_cmd)
    kver = kver_out.strip()

    # Determine debug file path
    if module == 'kernel':
        debug_file = f"/usr/lib/debug/lib/modules/{kver}/vmlinux"
    else:
        # Try to find module debug file
        find_cmd = f"find /usr/lib/debug/lib/modules/{kver} -name '{module}.ko.debug' 2>/dev/null | head -1"
        find_out, _ = run_remote_command(target_host, find_cmd)
        debug_file = find_out.strip()
        if not debug_file:
            find_cmd = f"find /usr/lib/debug/lib/modules/{kver} -name '{module}.ko' 2>/dev/null | head -1"
            find_out, _ = run_remote_command(target_host, find_cmd)
            debug_file = find_out.strip()

    if not debug_file:
        return None

    # Check if mangled symbol
    is_mangled = re.search(r'\.(isra|constprop|cold|part)\.\d+', symbol)

    if is_mangled:
        # Get base address from nm
        nm_cmd = f"nm {debug_file} 2>/dev/null | grep ' {symbol}$' | awk '{{print $1}}' | head -1"
        nm_out, _ = run_remote_command(target_host, nm_cmd)
        base_addr = nm_out.strip()

        if not base_addr:
            return None

        # Calculate target address
        target_addr = hex(int(base_addr, 16) + int(offset, 16))
        gdb_cmd = f"echo 'l *{target_addr}' | sudo gdb -q {debug_file} 2>&1"
    else:
        # Direct resolution
        gdb_cmd = f"echo 'l *({symbol}+{offset})' | sudo gdb -q {debug_file} 2>&1"

    output, rc = run_remote_command(target_host, gdb_cmd)

    # Check for actual GDB errors (not just 'error' in source code)
    if rc != 0:
        return None
    if 'No symbol' in output or 'Cannot access memory' in output:
        return None

    # Parse GDB output to extract file:line
    # Format: "0xffffffff817c1150 is in icmp_rcv (net/ipv4/icmp.c:1150)."
    match = re.search(r'is in (\S+) \(([^:]+):(\d+)\)', output)
    if match:
        return {
            'function': match.group(1),
            'file': match.group(2),
            'line': int(match.group(3)),
            'raw_output': output.strip()
        }

    return None


def read_source_context(kernel_source: str, file_path: str, line_num: int,
                        context_before: int = 15, context_after: int = 10) -> Optional[str]:
    """Read source code context around the given line."""
    full_path = Path(kernel_source) / file_path

    if not full_path.exists():
        return None

    try:
        with open(full_path, 'r') as f:
            lines = f.readlines()

        start = max(0, line_num - context_before - 1)
        end = min(len(lines), line_num + context_after)

        context_lines = []
        for i in range(start, end):
            marker = '>>>' if i == line_num - 1 else '   '
            context_lines.append(f"{marker} {i+1:4d}: {lines[i].rstrip()}")

        return '\n'.join(context_lines)
    except Exception as e:
        return f"ERROR reading source: {e}"


def classify_drop_context(source_context: str, resolution: Dict) -> Dict:
    """Classify whether the kfree_skb call is a true drop or normal processing."""
    classification = {
        'type': 'UNKNOWN',
        'confidence': 'low',
        'evidence': [],
        'reason': ''
    }

    if not source_context:
        return classification

    # Look for drop indicators
    drop_evidence = []
    normal_evidence = []

    # Check for drop labels in nearby code
    for label in DROP_LABELS:
        if re.search(rf'\b{label}\s*:', source_context, re.IGNORECASE):
            drop_evidence.append(f"Found '{label}:' label")

    # Check for normal processing labels
    for label in NORMAL_LABELS:
        if re.search(rf'\b{label}\s*:', source_context, re.IGNORECASE):
            normal_evidence.append(f"Found '{label}:' label")

    # Check for drop return values
    for ret in DROP_RETURNS:
        if ret in source_context:
            drop_evidence.append(f"Found return {ret}")

    # Check for drop statistics
    for stat in DROP_STATS:
        if stat in source_context:
            drop_evidence.append(f"Found drop stat {stat}")

    # Check for clone/copy operations (indicates operating on copy, not original)
    if re.search(r'(skb_clone|skb_copy|user_skb|nskb|alloc_skb)', source_context):
        normal_evidence.append("Operating on cloned/allocated buffer")

    # Check for success indicators
    if 'NET_RX_SUCCESS' in source_context or 'consume_skb' in source_context:
        normal_evidence.append("Found success path indicator")

    # Classify based on evidence
    if drop_evidence and not normal_evidence:
        classification['type'] = 'TRUE_DROP'
        classification['confidence'] = 'high'
        classification['evidence'] = drop_evidence
        classification['reason'] = '; '.join(drop_evidence)
    elif normal_evidence and not drop_evidence:
        classification['type'] = 'NORMAL_PROCESSING'
        classification['confidence'] = 'high'
        classification['evidence'] = normal_evidence
        classification['reason'] = '; '.join(normal_evidence)
    elif drop_evidence and normal_evidence:
        # Mixed signals - need manual review
        classification['type'] = 'NEEDS_REVIEW'
        classification['confidence'] = 'low'
        classification['evidence'] = drop_evidence + normal_evidence
        classification['reason'] = 'Mixed indicators found'
    else:
        classification['type'] = 'UNKNOWN'
        classification['confidence'] = 'low'
        classification['reason'] = 'No clear indicators found'

    return classification


def analyze_stack_trace(entry: Dict, target_host: str, kernel_source: str,
                        method: str = 'gdb') -> Dict:
    """Analyze a single stack trace entry."""
    result = {
        'stack_id': entry['stack_id'],
        'count': entry['count'],
        'device': entry['device'],
        'flow': entry.get('flow'),
        'resolution': None,
        'classification': None,
        'source_context': None
    }

    # Get the kfree_skb caller
    caller = entry.get('kfree_caller')
    if not caller:
        result['error'] = 'Could not identify kfree_skb caller'
        return result

    # Resolve to source line
    resolution = resolve_symbol_remote(
        target_host,
        caller['symbol'],
        caller['offset'],
        caller['module'],
        method
    )

    if not resolution:
        result['error'] = f"Failed to resolve {caller['symbol']}+{caller['offset']}"
        return result

    result['resolution'] = resolution

    # Read source context
    if kernel_source:
        source_context = read_source_context(
            kernel_source,
            resolution['file'],
            resolution['line']
        )
        result['source_context'] = source_context

        # Classify
        classification = classify_drop_context(source_context, resolution)
        result['classification'] = classification

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Analyze kernel stack traces from kfree_skb tracing tools'
    )
    parser.add_argument('--input', '-i', required=True,
                        help='Input file with tool output (or - for stdin)')
    parser.add_argument('--target', '-t', required=True,
                        help='SSH target host for resolution (e.g., smartx@192.168.70.31)')
    parser.add_argument('--kernel-source', '-k', default='../kernel',
                        help='Path to local kernel source (default: ../kernel)')
    parser.add_argument('--method', '-m', default='gdb', choices=['gdb', 'addr2line'],
                        help='Resolution method (default: gdb)')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output including source context')

    args = parser.parse_args()

    # Read input
    if args.input == '-':
        text = sys.stdin.read()
    else:
        with open(args.input, 'r') as f:
            text = f.read()

    # Parse
    parsed = parse_stack_output(text)

    # Add caller info
    for entry in parsed['entries']:
        caller = get_kfree_caller(entry)
        if caller:
            entry['kfree_caller'] = caller

    # Dedupe by stack_id
    seen_stacks = {}
    for entry in parsed['entries']:
        sid = entry['stack_id']
        if sid not in seen_stacks or entry['count'] > seen_stacks[sid]['count']:
            seen_stacks[sid] = entry

    unique_entries = list(seen_stacks.values())

    print(f"Parsed {len(unique_entries)} unique stack traces from input.", file=sys.stderr)
    print(f"Resolving addresses on {args.target}...", file=sys.stderr)

    # Analyze each unique stack
    results = []
    for entry in unique_entries:
        result = analyze_stack_trace(entry, args.target, args.kernel_source, args.method)
        results.append(result)

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n" + "=" * 60)
        print("Classification Results")
        print("=" * 60)

        drop_count = 0
        normal_count = 0
        unknown_count = 0

        for r in results:
            cls = r.get('classification') or {}
            cls_type = cls.get('type', 'UNKNOWN') if cls else 'UNKNOWN'
            total_calls = r['count']

            if cls_type == 'TRUE_DROP':
                drop_count += total_calls
            elif cls_type == 'NORMAL_PROCESSING':
                normal_count += total_calls
            else:
                unknown_count += total_calls

            print(f"\nStack #{r['stack_id']} ({r['count']} calls): {cls_type}")
            if r.get('flow'):
                print(f"  Flow: {r['flow']}")
            if r.get('resolution'):
                res = r['resolution']
                print(f"  Location: {res['file']}:{res['line']}")
            if cls and cls.get('reason'):
                print(f"  Reason: {cls['reason']}")
            if r.get('error'):
                print(f"  Error: {r['error']}")

            if args.verbose and r.get('source_context'):
                print(f"\n  Source context:")
                for line in r['source_context'].split('\n'):
                    print(f"    {line}")

        print("\n" + "-" * 60)
        print(f"Summary: {drop_count} TRUE_DROP, {normal_count} NORMAL_PROCESSING, {unknown_count} UNKNOWN")


if __name__ == '__main__':
    main()
