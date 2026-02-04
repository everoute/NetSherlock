# Data Path Model: System Network End-to-End

## Overview

This document defines the segment mapping for system network (host-to-host) ICMP latency analysis.
The model combines sender (TX mode) and receiver (RX mode) measurements to construct a complete
end-to-end latency breakdown.

## Complete Data Path Diagram

```
Sender Host                          Network                         Receiver Host
┌────────────────────────────┐      ┌─────────────────┐      ┌────────────────────────────┐
│ [S0] ip_send_skb           │      │                 │      │ [R0] netif_receive_skb     │
│   │                        │      │                 │      │   │                        │
│   ├── Sender ReqPath ──────┼──────┼── Wire (C) ─────┼──────┼───┤                        │
│   ▼                        │      │                 │      │   ▼                        │
│ [S1] phy TX                │      │                 │      │ [R1] icmp_rcv              │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├── Receiver Stack ──────│
│                            │      │                 │      │   ▼                        │
│                            │      │                 │      │ [R2] ip_send_skb           │
│                            │      │                 │      │   │                        │
│                            │      │                 │      │   ├── Receiver RepPath ────│
│                            │      │                 │      │   ▼                        │
│ [S2] phy RX                │◄─────┼── Wire (J) ─────┼──────┼── [R3] phy TX              │
│   │                        │      │                 │      │                            │
│   ├── Sender RepPath ──────│      │                 │      │                            │
│   ▼                        │      │                 │      │                            │
│ [S3] ping_rcv              │      │                 │      │                            │
└────────────────────────────┘      └─────────────────┘      └────────────────────────────┘
```

## RTT Calculation

```
Total RTT = Sender.Total = S3 - S0
          = Sender.ReqPath + Wire(C) + Receiver.RX_Processing + Wire(J) + Sender.RepPath
          = (S1-S0) + C + (R3-R0) + J + (S3-S2)
```

## Measurement Sources

### Sender Host (TX Mode)

| Segment | Formula | Description |
|---------|---------|-------------|
| Sender.ReqPath | S1 - S0 | ip_send_skb → phy TX |
| Sender.External | S2 - S1 | phy TX → phy RX (includes C + receiver processing + J) |
| Sender.RepPath | S3 - S2 | phy RX → ping_rcv |
| Sender.Total | S3 - S0 | Complete round-trip |

### Receiver Host (RX Mode)

| Segment | Formula | Description |
|---------|---------|-------------|
| Receiver.ReqPath | R1 - R0 | netif_receive_skb → icmp_rcv |
| Receiver.Stack | R2 - R1 | icmp_rcv → ip_send_skb (ICMP processing) |
| Receiver.RepPath | R3 - R2 | ip_send_skb → phy TX |
| Receiver.Total | R3 - R0 | Complete local processing |

## Wire Latency Derivation

Physical network latency cannot be directly measured but can be derived:

```
Wire(C) + Wire(J) = Sender.External - Receiver.Total
                  = (S2-S1) - (R3-R0)

Assuming symmetric network:
  Wire = (Sender.External - Receiver.Total) / 2
```

## Segment Mapping

| Segment | Source | Formula | Description |
|---------|--------|---------|-------------|
| A | Sender TX | S1 - S0 | Sender kernel → phy TX |
| C | Derived | (External - Receiver.Total) / 2 | Network transit (request) |
| D | Receiver RX | R1 - R0 | Receiver phy RX → icmp_rcv |
| E | Receiver RX | R2 - R1 | Receiver ICMP processing |
| F | Receiver RX | R3 - R2 | Receiver kernel → phy TX |
| J | Derived | (External - Receiver.Total) / 2 | Network transit (reply) |
| G | Sender TX | S3 - S2 | Sender phy RX → ping_rcv |

## Layer Attribution

| Layer | Segments | Description |
|-------|----------|-------------|
| Sender Host Internal | A, G | Sender host kernel processing |
| Receiver Host Internal | D, E, F | Receiver host kernel + ICMP processing |
| Physical Network | C, J | Wire/switch latency |

## Notes

1. **Segments C and J** (physical network) are derived from the difference between
   sender's External measurement and receiver's Total processing time.

2. **Asymmetric deployment** is required: sender runs in TX mode, receiver runs in RX mode.

3. **Validation**: The sum of all segments should equal the measured Total RTT within
   acceptable error margin (~10%).
