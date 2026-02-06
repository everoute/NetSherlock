# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-161937`
**Analysis Time**: 2026-02-06T16:20:30.768740

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 20252.60 µs (20.253 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 99.3% |
| **Sample Count** | 237 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 20117.70 | 99.3% | A, G |
| Receiver Host Internal | 107.20 | 0.5% | D, E, F |
| Physical Network | 27.70 | 0.1% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 20062.20 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 13.85 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 59.40 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 12.80 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 35.00 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 13.85 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 55.50 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │   20062.2µs          │      │      13.9µs    │      │   │      59.4µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      12.8µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      35.0µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      13.9µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      55.5µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 20252.6 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 20117.70 µs (99.3%)
- **Segments**: A, G

### ⚠️ High Latency
Total RTT (20252.6 µs) exceeds 1ms threshold.

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 20252.60 µs |
| Calculated Total | 20252.60 µs |
| Difference | 0.00 µs (0.00%) |
| Status | **Valid** |
