# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-190934`
**Analysis Time**: 2026-02-04T19:10:26.789288

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 272.30 µs (0.272 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 50.4% |
| **Sample Count** | 238 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 137.20 | 50.4% | A, G |
| Receiver Host Internal | 110.00 | 40.4% | D, E, F |
| Physical Network | 25.00 | 9.2% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 63.70 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.50 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 62.50 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 11.80 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 35.70 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.50 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 73.50 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      63.7µs          │      │      12.5µs    │      │   │      62.5µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      11.8µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      35.7µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.5µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      73.5µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 272.3 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 137.20 µs (50.4%)
- **Segments**: A, G

### ✅ Low Latency
Total RTT: 272.3 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 272.30 µs |
| Calculated Total | 272.20 µs |
| Difference | 0.10 µs (0.04%) |
| Status | **Valid** |
