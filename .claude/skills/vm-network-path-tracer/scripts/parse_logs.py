#!/usr/bin/env python3
"""Parse icmp_path_tracer logs for VM network drop detection.

icmp_path_tracer output format:
  Verbose per-flow:
    [TIMESTAMP] [ACTION] ID=N Seq=N ReqRX:Y ReqTX:Y RepRX:Y RepTX:Y
      Latency(us): ReqInternal=X.XX  External=X.XX  RepInternal=X.XX  Total=X.XX

  Drop events:
    === ICMP Drop Detected: TIMESTAMP ===
    Flow: SRC -> DST (ID=N, Seq=N)
    [0] ReqRX: recorded/MISSING
    ...
    Drop Location: Request dropped INTERNALLY

  Statistics:
    === ICMP Flow Statistics ===
    Total flows tracked: N
    Complete flows: N
    Request internal drops: N
    External drops: N
    Reply internal drops: N
"""

import json
import os
import re
import sys


def parse_vm_tracer_log(log_path: str) -> dict:
    """Parse a single icmp_path_tracer log file."""
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return {"error": f"Log file missing or empty: {log_path}", "total_flows": 0, "complete_flows": 0}

    with open(log_path, "r") as f:
        content = f.read()

    # Parse statistics summary
    stats = {}
    stats_patterns = {
        "total_flows": r"Total flows tracked:\s*(\d+)",
        "complete_flows": r"Complete flows:\s*(\d+)",
        "req_internal": r"Request internal drops:\s*(\d+)",
        "external": r"External drops:\s*(\d+)",
        "rep_internal": r"Reply internal drops:\s*(\d+)",
    }
    for key, pattern in stats_patterns.items():
        m = re.search(pattern, content)
        stats[key] = int(m.group(1)) if m else 0

    # Parse per-flow latencies
    latency_re = re.compile(
        r"Latency\(us\):\s*ReqInternal=([\d.]+)\s+External=([\d.]+)\s+RepInternal=([\d.]+)\s+Total=([\d.]+)"
    )
    req_internals = []
    externals = []
    rep_internals = []
    totals = []

    for m in latency_re.finditer(content):
        req_internals.append(float(m.group(1)))
        externals.append(float(m.group(2)))
        rep_internals.append(float(m.group(3)))
        totals.append(float(m.group(4)))

    def calc_stats(lst):
        if not lst:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "samples": 0}
        return {
            "avg": round(sum(lst) / len(lst), 3),
            "min": round(min(lst), 3),
            "max": round(max(lst), 3),
            "samples": len(lst),
        }

    drop_total = stats.get("req_internal", 0) + stats.get("external", 0) + stats.get("rep_internal", 0)
    total = stats.get("total_flows", 0)
    drop_rate = round(drop_total / total, 4) if total > 0 else 0.0

    return {
        "total_flows": stats.get("total_flows", 0),
        "complete_flows": stats.get("complete_flows", 0),
        "drops": {
            "req_internal": stats.get("req_internal", 0),
            "external": stats.get("external", 0),
            "rep_internal": stats.get("rep_internal", 0),
        },
        "drop_rate": drop_rate,
        "latency_us": {
            "req_internal": calc_stats(req_internals),
            "external": calc_stats(externals),
            "rep_internal": calc_stats(rep_internals),
            "total": calc_stats(totals),
        },
    }


def parse_vm_drop_logs(measurement_dir: str) -> dict:
    """Parse all logs in a vm-network-path-tracer measurement directory."""
    sender = parse_vm_tracer_log(os.path.join(measurement_dir, "sender-host.log"))
    receiver = parse_vm_tracer_log(os.path.join(measurement_dir, "receiver-host.log"))

    sender["boundary"] = "vnet→phy (VM outbound)"
    receiver["boundary"] = "phy→vnet (VM inbound)"

    return {
        "measurement_type": "vm-network-path-tracer",
        "sender": sender,
        "receiver": receiver,
        "log_files": ["sender-host.log", "receiver-host.log"],
        "measurement_dir": measurement_dir,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <measurement_dir>", file=sys.stderr)
        sys.exit(1)
    result = parse_vm_drop_logs(sys.argv[1])
    print(json.dumps(result, indent=2))
