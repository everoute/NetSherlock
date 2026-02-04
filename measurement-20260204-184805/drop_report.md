# System Network Drop Analysis Report

**Measurement Directory**: `measurement-20260204-184805`
**Analysis Time**: 2026-02-04T18:49:21.464024

## Summary

| Metric | Value |
|--------|-------|
| **Total Drops** | 0 |
| **Drop Rate** | 0.00% |
| **Total Flows** | 211 |
| **Complete Flows** | 211 |

## Drop Breakdown by Type

### Sender Host (TX Mode)

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 0 | Outbound: stack → phy TX |
| drop_1_2 | 0 | External: network or peer |
| drop_2_3 | 0 | Inbound: phy RX → stack |

### Receiver Host (RX Mode)

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 0 | Inbound: phy RX → icmp_rcv |
| drop_1_2 | 0 | Stack: no reply generated |
| drop_2_3 | 0 | Outbound: ip_send_skb → phy TX |

## Pattern Analysis

- **Pattern Type**: none
- **Burst Events**: 0
- **Sporadic Events**: 0
- **Average Interval**: 0.0 ms

## Recommendations

- No drops detected - network path is stable
