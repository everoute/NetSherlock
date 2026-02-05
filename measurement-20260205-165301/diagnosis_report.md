# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260205-165301`
**Analysis Time**: 2026-02-05T16:54:52.932650

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 20237.90 µs (20.238 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 99.4% |
| **Sample Count** | 237 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 20109.40 | 99.4% | A, G |
| Receiver Host Internal | 104.80 | 0.5% | D, E, F |
| Physical Network | 23.70 | 0.1% | C, J |

## Segment Breakdown

| Segment | Name | Latency (µs) | Source | Description |
|---------|------|-------------|--------|-------------|
| A | Sender ReqPath | 20055.30 | sender_tx | Sender kernel TX processing (ip_send_skb |
| C | Wire (Request) | 11.85 | derived | Physical network transit (request direct |
| D | Receiver ReqPath | 58.90 | receiver_rx | Receiver kernel RX processing (phy RX →  |
| E | Receiver Stack | 12.60 | receiver_rx | Receiver ICMP echo processing (icmp_rcv  |
| F | Receiver RepPath | 33.30 | receiver_rx | Receiver kernel TX processing (ip_send_s |
| J | Wire (Reply) | 11.85 | derived | Physical network transit (reply directio |
| G | Sender RepPath | 54.10 | sender_tx | Sender kernel RX processing (phy RX → pi |

## Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [A] ip_send_skb            │      │                 │      │ [D] netif_receive_skb      │
│   │                        │      │                 │      │   │                        │
│   ├─ Sender ReqPath ───────┼──────┼── Wire [C] ─────┼──────┼───┤  Receiver ReqPath      │
│   │   20055.3µs          │      │      11.9µs    │      │   │      58.9µs          │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [E] icmp_rcv               │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver Stack ───────│
│                            │      │                 │      │   │      12.6µs          │
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [F] ip_send_skb            │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├─ Receiver RepPath ─────│
│                            │      │                 │      │   │      33.3µs          │
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire [J] ─────┼──────┼── [R3] phy TX              │
│   │                        │      │      11.9µs    │      │                            │
│   ├─ Sender RepPath ───────│      │                 │      │                            │
│   │      54.1µs          │      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [G] ping_rcv               │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘

Total RTT = A + C + D + E + F + J + G = 20237.9 µs
```

## Drop Statistics

✅ No packet drops detected during measurement period.

## Key Findings

### Primary Latency Contributor

- **Layer**: Sender Host Internal
- **Latency**: 20109.40 µs (99.4%)
- **Segments**: A, G

### ⚠️ High Latency
Total RTT (20237.9 µs) exceeds 1ms threshold.

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 20237.90 µs |
| Calculated Total | 20237.90 µs |
| Difference | 0.00 µs (0.00%) |
| Status | **Valid** |
