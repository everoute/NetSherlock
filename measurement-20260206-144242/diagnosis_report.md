# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-144242`
**Analysis Time**: 2026-02-06T14:43:35.449656

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 20247.90 µs (20.248 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 99.4% |
| **Sample Count** | 235 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 20120.90 | 99.4% | A, G |
| Receiver Host Internal | 102.60 | 0.5% | D, E, F |
| Physical Network | 24.30 | 0.1% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 20064.10 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.15 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 57.60 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 11.20 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 33.80 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.15 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 56.80 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │   20064.1µs          │      │      12.2µs    │      │   │      57.6µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      11.2µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      33.8µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.2µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      56.8µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 20247.9 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 20120.90 µs (99.4%)
- **Segments**: A, G

### ⚠️ High Latency
Total RTT (20247.9 µs) exceeds 1ms threshold.

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 20247.90 µs |
| Calculated Total | 20247.80 µs |
| Difference | 0.10 µs (0.00%) |
| Status | **Valid** |
