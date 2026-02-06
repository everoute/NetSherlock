# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-144936`
**Analysis Time**: 2026-02-06T14:50:30.477172

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 237.60 µs (0.238 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 45.3% |
| **Sample Count** | 214 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 107.70 | 45.3% | A, G |
| Receiver Host Internal | 105.10 | 44.3% | D, E, F |
| Physical Network | 24.70 | 10.4% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 53.20 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 12.35 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 59.30 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 11.80 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 34.00 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 12.35 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 54.50 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │      53.2µs          │      │      12.4µs    │      │   │      59.3µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      11.8µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      34.0µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      12.4µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      54.5µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 237.6 µs
```

## Drop Statistics

| Location | Type | Count |
|----------|------|-------|
| Sender | internal_request | **21** |

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 107.70 µs (45.3%)
- **Segments**: A, G

### ✅ Low Latency
Total RTT: 237.6 µs (excellent)

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 237.60 µs |
| Calculated Total | 237.50 µs |
| Difference | 0.10 µs (0.04%) |
| Status | **Valid** |
