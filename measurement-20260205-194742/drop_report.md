# System Network Drop Analysis Report

**Measurement Directory**: `measurement-20260205-194742`
**Analysis Time**: 2026-02-05T19:48:36.455491

## Summary

| Metric | Value |
|--------|-------|
| **Total Drops** | 26 |
| **Drop Rate** | 5.75% |
| **Total Flows** | 452 |
| **Complete Flows** | 426 |

## Drop Location Attribution

| Layer | Drops | Percentage | Drop Types |
|-------|-------|------------|------------|
| Sender Host Internal | **26** | 100.0% | Outbound (stack→phy), Inbound (phy→stack) |

## Drop Breakdown by Type

### Sender Host (TX Mode)

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 26 | Outbound: stack → phy TX |
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
- **Burst Events**: 7
- **Sporadic Events**: 10
- **Average Interval**: 1015.4 ms

### Burst Details

| # | Start Time | Duration (ms) | Drop Count |
|---|------------|---------------|------------|
| 1 | 2026-02-05T19:48:02.033000 | 1.0 | 3 |
| 2 | 2026-02-05T19:48:04.198000 | 0.0 | 2 |
| 3 | 2026-02-05T19:48:05.279000 | 0.0 | 2 |
| 4 | 2026-02-05T19:48:08.527000 | 0.0 | 3 |
| 5 | 2026-02-05T19:48:11.719000 | 0.0 | 2 |
| 6 | 2026-02-05T19:48:18.085000 | 0.0 | 2 |
| 7 | 2026-02-05T19:48:20.133000 | 0.0 | 2 |

## Drop Timeline

| Time | Flow | Seq | Location | Description |
|------|------|-----|----------|-------------|
| 2026-02-05T19:47:59.868 | 70.0.0.32 → 70.0.0.31 | 585 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:00.949 | 70.0.0.32 → 70.0.0.31 | 8 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:02.033 | 70.0.0.32 → 70.0.0.31 | 9 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:02.033 | 70.0.0.32 → 70.0.0.31 | 123 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:02.034 | 70.0.0.32 → 70.0.0.31 | 129 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:03.118 | 70.0.0.32 → 70.0.0.31 | 177 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:04.198 | 70.0.0.32 → 70.0.0.31 | 213 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:04.198 | 70.0.0.32 → 70.0.0.31 | 11 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:05.279 | 70.0.0.32 → 70.0.0.31 | 261 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:05.279 | 70.0.0.32 → 70.0.0.31 | 291 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:06.362 | 70.0.0.32 → 70.0.0.31 | 327 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:07.446 | 70.0.0.32 → 70.0.0.31 | 381 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:08.527 | 70.0.0.32 → 70.0.0.31 | 417 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:08.527 | 70.0.0.32 → 70.0.0.31 | 429 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:08.527 | 70.0.0.32 → 70.0.0.31 | 441 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:09.607 | 70.0.0.32 → 70.0.0.31 | 483 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:11.719 | 70.0.0.32 → 70.0.0.31 | 585 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:11.719 | 70.0.0.32 → 70.0.0.31 | 597 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:17.039 | 70.0.0.32 → 70.0.0.31 | 123 | unknown | Request dropped INTERNALLY (ip |
| 2026-02-05T19:48:18.085 | 70.0.0.32 → 70.0.0.31 | 177 | unknown | Request dropped INTERNALLY (ip |
| ... | *6 more events* | | | |

## Recommendations

- Investigate Sender Host: 26 drops (100.0%) - check CPU load, memory pressure, NIC driver
- Burst drop pattern detected (7 bursts) - likely transient congestion or resource exhaustion
