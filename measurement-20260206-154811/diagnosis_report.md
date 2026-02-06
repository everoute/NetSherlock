# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-154811`
**Analysis Time**: 2026-02-06T15:49:04.918345

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 20245.90 µs (20.246 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 99.4% |
| **Sample Count** | 237 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 20114.50 | 99.4% | A, G |
| Receiver Host Internal | 106.20 | 0.5% | D, E, F |
| Physical Network | 25.20 | 0.1% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 20058.90 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.60 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 59.90 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 12.40 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 33.90 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.60 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 55.60 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │   20058.9µs          │      │      12.6µs    │      │   │      59.9µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      12.4µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      33.9µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.6µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      55.6µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 20245.9 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 20114.50 µs (99.4%)
- **Segments**: A, G

### ⚠️ High Latency
Total RTT (20245.9 µs) exceeds 1ms threshold.

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 20245.90 µs |
| Calculated Total | 20245.90 µs |
| Difference | 0.00 µs (0.00%) |
| Status | **Valid** |
