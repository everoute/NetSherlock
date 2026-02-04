# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-175710`
**Analysis Time**: 2026-02-04T17:58:02.314063

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 227.50 µs (0.228 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 45.3% |
| **Sample Count** | 228 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 103.00 | 45.3% | A, G |
| Receiver Host Internal | 98.80 | 43.4% | D, E, F |
| Physical Network | 25.60 | 11.3% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 48.90 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.80 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 57.60 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 9.80 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 31.40 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.80 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 54.10 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      48.9µs          │      │      12.8µs    │      │   │      57.6µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │       9.8µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      31.4µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.8µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      54.1µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 227.5 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 103.00 µs (45.3%)
- **Segments**: A, G

### ✅ Low Latency
Total RTT: 227.5 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 227.50 µs |
| Calculated Total | 227.40 µs |
| Difference | 0.10 µs (0.04%) |
| Status | **Valid** |
