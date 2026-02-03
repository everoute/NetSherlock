#!/usr/bin/env python3
"""Parse system_icmp_path_tracer log files for drop statistics and latency.

Output format from the tool:
  Verbose per-flow:
    TIMESTAMP [ACTION] ID=N Seq=N ReqRX@phy:Y ReqRcv@stack:Y RepSnd@stack:Y RepTX@phy:Y
      Latency(us): ReqPath=X.X Stack=X.X RepPath=X.X Total=X.X

  Drop events:
    === ICMP Drop Detected: TIMESTAMP ===
    Flow: SRC -> DST (ID=N, Seq=N)
      [0] ReqRX@phy: recorded
      [1] ReqRcv@stack: MISSING
    Drop: Request dropped INTERNALLY (between phy NIC and icmp_rcv)

  Statistics (on Ctrl-C):
    === ICMP System Path Statistics ===
    Total flows tracked: N
    Complete flows: N
    Request internal drops: N
    Stack no-reply: N
    Reply internal drops: N
"""

import json
import os
import re
import sys


def parse_system_tracer_log(log_path: str) -> dict:
    """Parse a single system_icmp_path_tracer log file."""
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return {"error": f"Log file missing or empty: {log_path}", "total_flows": 0, "complete_flows": 0}

    with open(log_path, "r") as f:
        content = f.read()

    # Parse statistics summary (most reliable source)
    stats = {}
    stats_patterns = {
        "total_flows": r"Total flows tracked:\s*(\d+)",
        "complete_flows": r"Complete flows:\s*(\d+)",
        "req_internal": r"Request internal drops:\s*(\d+)",
        "stack_no_reply": r"Stack no-reply:\s*(\d+)",
        "rep_internal": r"Reply internal drops:\s*(\d+)",
    }
    for key, pattern in stats_patterns.items():
        m = re.search(pattern, content)
        stats[key] = int(m.group(1)) if m else 0

    # Parse per-flow latencies from verbose output
    latency_re = re.compile(
        r"Latency\(us\):\s*ReqPath=([\d.]+)\s+Stack=([\d.]+)\s+RepPath=([\d.]+)\s+Total=([\d.]+)"
    )
    req_paths = []
    stacks = []
    rep_paths = []
    totals = []

    for m in latency_re.finditer(content):
        req_paths.append(float(m.group(1)))
        stacks.append(float(m.group(2)))
        rep_paths.append(float(m.group(3)))
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

    drop_total = stats.get("req_internal", 0) + stats.get("stack_no_reply", 0) + stats.get("rep_internal", 0)
    total = stats.get("total_flows", 0)
    drop_rate = round(drop_total / total, 4) if total > 0 else 0.0

    return {
        "total_flows": stats.get("total_flows", 0),
        "complete_flows": stats.get("complete_flows", 0),
        "drops": {
            "req_internal": stats.get("req_internal", 0),
            "stack_no_reply": stats.get("stack_no_reply", 0),
            "rep_internal": stats.get("rep_internal", 0),
        },
        "drop_rate": drop_rate,
        "latency_us": {
            "req_path": calc_stats(req_paths),
            "stack": calc_stats(stacks),
            "rep_path": calc_stats(rep_paths),
            "total": calc_stats(totals),
        },
    }


def parse_system_drop_logs(measurement_dir: str) -> dict:
    """Parse all logs in a system-network-path-tracer measurement directory."""
    receiver = parse_system_tracer_log(os.path.join(measurement_dir, "receiver-host.log"))
    sender = parse_system_tracer_log(os.path.join(measurement_dir, "sender-host.log"))

    receiver["role"] = "primary (traces A→B traffic)"
    sender["role"] = "secondary (traces B→A traffic)"

    return {
        "measurement_type": "system-network-path-tracer",
        "receiver": receiver,
        "sender": sender,
        "log_files": ["receiver-host.log", "sender-host.log"],
        "measurement_dir": measurement_dir,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <measurement_dir>", file=sys.stderr)
        sys.exit(1)
    result = parse_system_drop_logs(sys.argv[1])
    print(json.dumps(result, indent=2))
