# System Network Drop Analysis Report

**Measurement Directory**: `measurement-20260206-145210`
**Analysis Time**: 2026-02-06T14:53:01.994347

## Summary

| Metric | Value |
|--------|-------|
| **Total Drops** | 30 |
| **Drop Rate** | 6.67% |
| **Total Flows** | 450 |
| **Complete Flows** | 420 |

## Drop Location Attribution

| Layer | Drops | Percentage | Drop Types |
|-------|-------|------------|------------|
| Sender Host Internal | **30** | 100.0% | Outbound (stack→phy), Inbound (phy→stack) |

## Drop Breakdown by Type

### Sender Host (TX Mode)

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 30 | Outbound: stack → phy TX |
| drop_1_2 | 0 | External: network or peer |
| drop_2_3 | 0 | Inbound: phy RX → stack |

### Receiver Host (RX Mode)

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 0 | Inbound: phy RX → icmp_rcv |
| drop_1_2 | 0 | Stack: no reply generated |
| drop_2_3 | 0 | Outbound: ip_send_skb → phy TX |

## Pattern Analysis

- **Pattern Type**: burst
- **Burst Events**: 10
- **Sporadic Events**: 7
- **Average Interval**: 868.8 ms

### Burst Details

| # | Start Time | Duration (ms) | Drop Count |
|---|------------|---------------|------------|
| 1 | 2026-02-06T14:52:33.032000 | 0.0 | 3 |
| 2 | 2026-02-06T14:52:35.199000 | 0.0 | 2 |
| 3 | 2026-02-06T14:52:37.348000 | 0.0 | 2 |
| 4 | 2026-02-06T14:52:42.628000 | 0.0 | 2 |
| 5 | 2026-02-06T14:52:43.685000 | 0.0 | 3 |
| 6 | 2026-02-06T14:52:44.688000 | 0.0 | 2 |
| 7 | 2026-02-06T14:52:46.738000 | 0.0 | 2 |
| 8 | 2026-02-06T14:52:47.781000 | 0.0 | 3 |
| 9 | 2026-02-06T14:52:49.829000 | 0.0 | 2 |
| 10 | 2026-02-06T14:52:50.845000 | 0.0 | 2 |

## Drop Timeline

| Time | Flow | Seq | Location | Description |
|------|------|-----|----------|-------------|
| 2026-02-06T14:52:28.704 | 70.0.0.32 → 70.0.0.31 | 147 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:29.785 | 70.0.0.32 → 70.0.0.31 | 189 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:30.870 | 70.0.0.32 → 70.0.0.31 | 9 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:33.032 | 70.0.0.32 → 70.0.0.31 | 327 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:33.032 | 70.0.0.32 → 70.0.0.31 | 11 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:33.032 | 70.0.0.32 → 70.0.0.31 | 357 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:35.199 | 70.0.0.32 → 70.0.0.31 | 447 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:35.199 | 70.0.0.32 → 70.0.0.31 | 459 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:37.348 | 70.0.0.32 → 70.0.0.31 | 543 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:37.348 | 70.0.0.32 → 70.0.0.31 | 567 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:41.546 | 70.0.0.32 → 70.0.0.31 | 39 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:42.628 | 70.0.0.32 → 70.0.0.31 | 75 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:42.628 | 70.0.0.32 → 70.0.0.31 | 93 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:43.685 | 70.0.0.32 → 70.0.0.31 | 129 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:43.685 | 70.0.0.32 → 70.0.0.31 | 141 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:43.685 | 70.0.0.32 → 70.0.0.31 | 153 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:44.688 | 70.0.0.32 → 70.0.0.31 | 183 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:44.688 | 70.0.0.32 → 70.0.0.31 | 23 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:45.733 | 70.0.0.32 → 70.0.0.31 | 255 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-06T14:52:46.738 | 70.0.0.32 → 70.0.0.31 | 303 | unknown | Request dropped INTERNALLY (ip |
| ... | *10 more events* | | | |

## Recommendations

- Investigate Sender Host: 30 drops (100.0%) - check CPU load, memory pressure, NIC driver
- Burst drop pattern detected (10 bursts) - likely transient congestion or resource exhaustion
