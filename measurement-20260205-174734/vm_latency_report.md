# VM Network Latency Analysis Report

**Measurement Directory**: `measurement-20260205-174734`
**Analysis Time**: 2026-02-05T17:48:32.760644

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 20383.00 us |
| **Receiver Total RTT** | 239.40 us |
| **Physical Network (derived)** | 28.50 us |
| **Primary Contributor** | Sender Host OVS |
| **Sample Count** | 49 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host OVS | 20115.10 | 98.7% | S_ReqInternal, S_RepInternal |
| Receiver Host OVS | 120.70 | 0.6% | R_ReqInternal, R_RepInternal |
| Receiver VM + Virtualization | 118.70 | 0.6% | R_External |
| Physical Network | 28.50 | 0.1% | Physical |

*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*

## Segment Breakdown

| Segment | Latency (us) | Source | Description |
|---------|-------------|--------|-------------|
| Sender ReqInternal | 20068.40 | sender_host | Sender Host: vnet→phy (OVS forwarding, r |
| Physical Network | 28.50 | derived | Wire latency (both directions) |
| Receiver ReqInternal | 71.80 | receiver_host | Receiver Host: phy→vnet (OVS forwarding, |
| Receiver External | 118.70 | receiver_host | Receiver: vnet→VM→vnet (VM + virtualizat |
| Receiver RepInternal | 48.90 | receiver_host | Receiver Host: vnet→phy (OVS forwarding, |
| Sender RepInternal | 46.70 | sender_host | Sender Host: phy→vnet (OVS forwarding, r |

## Data Path Diagram

```
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal: 20068.4us]      [Physical:   28.5us]      [R.ReqInternal:   71.8us]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                        118.7us
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal:   46.7us]                                [R.RepInternal:   48.9us]

Sender Total: 20383.0us | Receiver Total: 239.4us
Physical Network (derived) = Sender.External - Receiver.Total = 28.5us
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
```

## Key Findings

- **Primary Bottleneck**: Sender Host OVS (20115.1us, 98.7%)
- **Physical Network**: 28.5us - within normal range
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)
