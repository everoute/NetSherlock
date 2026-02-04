# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-190717`
**Analysis Time**: 2026-02-04T19:08:09.633028

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 263.30 µs (0.263 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 50.3% |
| **Sample Count** | 232 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 132.40 | 50.3% | A, G |
| Receiver Host Internal | 106.30 | 40.4% | D, E, F |
| Physical Network | 24.60 | 9.3% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 60.70 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.30 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 60.30 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 11.80 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 34.20 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.30 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 71.70 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      60.7µs          │      │      12.3µs    │      │   │      60.3µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      11.8µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      34.2µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.3µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      71.7µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 263.3 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 132.40 µs (50.3%)
- **Segments**: A, G

### ✅ Low Latency
Total RTT: 263.3 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 263.30 µs |
| Calculated Total | 263.30 µs |
| Difference | 0.00 µs (0.00%) |
| Status | **Valid** |
