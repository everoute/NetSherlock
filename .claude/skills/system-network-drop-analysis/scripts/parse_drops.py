#!/usr/bin/env python3
"""Parse drop events from system_icmp_path_tracer verbose output.

Extracts per-drop event details including:
- Timestamp
- Flow identification (src_ip, dst_ip, icmp_id, seq)
- Drop location (drop_0_1, drop_1_2, drop_2_3)
- Stage timestamps (which stages were captured)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DropEvent:
    """Single packet drop event."""
    timestamp: datetime
    src_ip: str
    dst_ip: str
    icmp_id: int
    seq: int
    drop_type: str  # drop_0_1, drop_1_2, drop_2_3
    direction: str  # rx or tx
    description: str
    stages_seen: list[int]  # Which stages had timestamps


@dataclass
class DropStats:
    """Aggregated drop statistics from summary block."""
    total_flows: int
    complete_flows: int
    drop_0_1: int  # Request internal drops
    drop_1_2: int  # Stack no-reply (RX) or External (TX)
    drop_2_3: int  # Reply internal drops

    @property
    def total_drops(self) -> int:
        return self.drop_0_1 + self.drop_1_2 + self.drop_2_3

    @property
    def drop_rate(self) -> float:
        if self.total_flows == 0:
            return 0.0
        return self.total_drops / self.total_flows


def detect_direction(content: str) -> str:
    """Detect RX or TX direction from log content."""
    if "Direction: TX" in content:
        return "tx"
    return "rx"


def parse_drop_events(content: str, direction: Optional[str] = None) -> list[DropEvent]:
    """Parse individual drop events from verbose output.

    Drop event format:
    === ICMP Drop Detected: 2026-02-04 12:29:00.123 ===
    Flow: 192.168.70.32 -> 192.168.70.31 (ID=62206, Seq=399)
      [0] ReqRX@phy: 1707012540123456789 ns
      [1] ReqRcv@stack: 0 (missing)
      ...
    Drop: Request dropped INTERNALLY (phy NIC -> icmp_rcv)
    """
    if direction is None:
        direction = detect_direction(content)

    events = []

    # Pattern to match drop event blocks
    drop_block_re = re.compile(
        r'=== ICMP Drop Detected: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) ===\s*'
        r'Flow: ([\d.]+) -> ([\d.]+) \(ID=(\d+), Seq=(\d+)\)\s*'
        r'((?:\s*\[\d\][^\n]+\n)+)'
        r'\s*Drop: ([^\n]+)',
        re.MULTILINE
    )

    for match in drop_block_re.finditer(content):
        ts_str, src_ip, dst_ip, icmp_id, seq, stages_block, drop_desc = match.groups()

        # Parse timestamp
        try:
            timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            timestamp = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")

        # Parse which stages were seen
        stages_seen = []
        for stage_match in re.finditer(r'\[(\d)\][^:]+:\s*(\d+|0 \(missing\))', stages_block):
            stage_num = int(stage_match.group(1))
            stage_val = stage_match.group(2)
            if stage_val != "0 (missing)" and stage_val != "0":
                stages_seen.append(stage_num)

        # Determine drop type from stages seen
        if 0 in stages_seen and 1 not in stages_seen:
            drop_type = "drop_0_1"
        elif 1 in stages_seen and 2 not in stages_seen:
            drop_type = "drop_1_2"
        elif 2 in stages_seen and 3 not in stages_seen:
            drop_type = "drop_2_3"
        else:
            drop_type = "unknown"

        events.append(DropEvent(
            timestamp=timestamp,
            src_ip=src_ip,
            dst_ip=dst_ip,
            icmp_id=int(icmp_id),
            seq=int(seq),
            drop_type=drop_type,
            direction=direction,
            description=drop_desc.strip(),
            stages_seen=stages_seen,
        ))

    return events


def parse_drop_stats(content: str, direction: Optional[str] = None) -> DropStats:
    """Parse statistics summary block."""
    if direction is None:
        direction = detect_direction(content)

    def extract_int(pattern: str) -> int:
        match = re.search(pattern, content)
        return int(match.group(1)) if match else 0

    total_flows = extract_int(r'Total flows tracked:\s*(\d+)')
    complete_flows = extract_int(r'Complete flows:\s*(\d+)')
    drop_0_1 = extract_int(r'Request internal drops:\s*(\d+)')
    drop_2_3 = extract_int(r'Reply internal drops:\s*(\d+)')

    # Middle drop varies by direction
    if direction == "rx":
        drop_1_2 = extract_int(r'Stack no-reply:\s*(\d+)')
    else:
        drop_1_2 = extract_int(r'External drops:\s*(\d+)')

    return DropStats(
        total_flows=total_flows,
        complete_flows=complete_flows,
        drop_0_1=drop_0_1,
        drop_1_2=drop_1_2,
        drop_2_3=drop_2_3,
    )


def parse_log_file(content: str, direction: Optional[str] = None) -> dict:
    """Parse a complete log file for drops.

    Returns dict with events list and stats.
    """
    if direction is None:
        direction = detect_direction(content)

    events = parse_drop_events(content, direction)
    stats = parse_drop_stats(content, direction)

    return {
        "direction": direction,
        "events": events,
        "stats": stats,
    }
