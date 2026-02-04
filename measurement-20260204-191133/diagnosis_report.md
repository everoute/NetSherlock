# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-191133`
**Analysis Time**: 2026-02-04T19:12:24.989263

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 277.60 µs (0.278 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 51.2% |
| **Sample Count** | 233 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 142.00 | 51.2% | A, G |
| Receiver Host Internal | 109.20 | 39.3% | D, E, F |
| Physical Network | 26.40 | 9.5% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 63.30 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 13.20 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 61.50 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 11.50 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 36.20 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 13.20 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 78.70 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      63.3µs          │      │      13.2µs    │      │   │      61.5µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      11.5µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      36.2µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      13.2µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      78.7µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 277.6 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 142.00 µs (51.2%)
- **Segments**: A, G

### ✅ Low Latency
Total RTT: 277.6 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 277.60 µs |
| Calculated Total | 277.60 µs |
| Difference | 0.00 µs (0.00%) |
| Status | **Valid** |
