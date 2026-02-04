# VM Network Latency Analysis Report

**Measurement Directory**: `measurement-20260204-175008`
**Analysis Time**: 2026-02-04T17:51:07.441925

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 353.80 us |
| **Receiver Total RTT** | 229.00 us |
| **Physical Network (derived)** | 23.00 us |
| **Primary Contributor** | Receiver Host OVS |
| **Sample Count** | 24 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver Host OVS | 118.00 | 33.4% | R_ReqInternal, R_RepInternal |
| Receiver VM + Virtualization | 111.00 | 31.4% | R_External |
| Sender Host OVS | 101.80 | 28.8% | S_ReqInternal, S_RepInternal |
| Physical Network | 23.00 | 6.5% | Physical |

*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*

## Segment Breakdown

| Segment | Latency (us) | Source | Description |
|---------|-------------|--------|-------------|
| Sender ReqInternal | 57.90 | sender_host | Sender Host: vnet→phy (OVS forwarding, r |
| Physical Network | 23.00 | derived | Wire latency (both directions) |
| Receiver ReqInternal | 71.00 | receiver_host | Receiver Host: phy→vnet (OVS forwarding, |
| Receiver External | 111.00 | receiver_host | Receiver: vnet→VM→vnet (VM + virtualizat |
| Receiver RepInternal | 47.00 | receiver_host | Receiver Host: vnet→phy (OVS forwarding, |
| Sender RepInternal | 43.90 | sender_host | Sender Host: phy→vnet (OVS forwarding, r |

## Data Path Diagram

```
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal:   57.9us]      [Physical:   23.0us]      [R.ReqInternal:   71.0us]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                        111.0us
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal:   43.9us]                                [R.RepInternal:   47.0us]

Sender Total: 353.8us | Receiver Total: 229.0us
Physical Network (derived) = Sender.External - Receiver.Total = 23.0us
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
```

## Key Findings

- **Primary Bottleneck**: Receiver Host OVS (118.0us, 33.4%)
- **Physical Network**: 23.0us - within normal range
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)
