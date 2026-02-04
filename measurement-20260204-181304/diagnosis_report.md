# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-181304`
**Analysis Time**: 2026-02-04T18:14:17.540602

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 229.30 µs (0.229 ms) |
| **Primary Contributor** | Receiver Host Internal |
| **Contribution** | 44.5% |
| **Sample Count** | 235 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver Host Internal | 101.90 | 44.5% | D, E, F |
| Sender Host Internal | 100.10 | 43.7% | A, G |
| Physical Network | 27.20 | 11.9% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 48.70 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 13.60 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 58.40 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 10.10 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 33.40 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 13.60 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 51.40 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      48.7µs          │      │      13.6µs    │      │   │      58.4µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      10.1µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      33.4µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      13.6µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      51.4µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 229.3 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Receiver Host Internal
- **Latency**: 101.90 µs (44.5%)
- **Segments**: D, E, F

### ✅ Low Latency
Total RTT: 229.3 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 229.30 µs |
| Calculated Total | 229.20 µs |
| Difference | 0.10 µs (0.04%) |
| Status | **Valid** |
