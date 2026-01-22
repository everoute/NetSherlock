# Data Path Model

## Overview

This document defines the 13 segments (A-M) of the cross-node VM ICMP ping data path.

## Complete Data Path Diagram

```
                          ICMP Request Path
  ┌─────────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                     │
  │  Sender VM (VM-A)                                                                   │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [A] icmp_send → tcp/ip stack → virtio-net TX                               │   │
  │  │      (kernel_icmp_rtt Path 1)                                                │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Sender Host (Host-A)                                                               │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [B_1] KVM ioeventfd → vhost handle_tx_kick → tun_sendmsg → netif_receive   │   │
  │  │        (kvm_vhost_tun_latency_details: S0+S1+S2)                            │   │
  │  │                                                                              │   │
  │  │  [B] vnet RX → OVS/bridge → physical NIC TX                                 │   │
  │  │      (icmp_drop_detector ReqInternal: vnet→phy)                             │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Network                                                                            │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [C] Physical wire / switch latency                                         │   │
  │  │      (Derived from External measurements)                                   │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Receiver Host (Host-B)                                                             │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [D] physical NIC RX → OVS/bridge → vnet TX                                 │   │
  │  │      (icmp_drop_detector ReqInternal: phy→vnet)                             │   │
  │  │                                                                              │   │
  │  │  [E] tun_net_xmit → vhost_signal → eventfd → irqfd → KVM IRQ injection      │   │
  │  │      (tun_tx_to_kvm_irq: S1→S5)                                             │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Receiver VM (VM-B)                                                                 │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [F] virtio-net RX → tcp/ip stack → icmp_rcv                                │   │
  │  │      (kernel_icmp_rtt Path 1)                                                │   │
  │  │                                                                              │   │
  │  │  [G] ICMP echo request processing → echo reply generation                   │   │
  │  │      (kernel_icmp_rtt Inter-Path)                                            │   │
  │  │                                                                              │   │
  │  │  [H] icmp_reply → tcp/ip stack → virtio-net TX                              │   │
  │  │      (kernel_icmp_rtt Path 2)                                                │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                                                                                     │
  └─────────────────────────────────────────────────────────────────────────────────────┘

                          ICMP Reply Path (reverse)
  ┌─────────────────────────────────────────────────────────────────────────────────────┐
  │                                                                                     │
  │  Receiver Host (Host-B)                                                             │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [I_1] KVM ioeventfd → vhost handle_tx_kick → tun_sendmsg → netif_receive   │   │
  │  │        (kvm_vhost_tun_latency_details: S0+S1+S2)                            │   │
  │  │                                                                              │   │
  │  │  [I] vnet RX → OVS/bridge → physical NIC TX                                 │   │
  │  │      (icmp_drop_detector RepInternal: vnet→phy on recv-host)                │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Network                                                                            │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [J] Physical wire / switch latency (reply direction)                       │   │
  │  │      (Derived from External measurements)                                   │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Sender Host (Host-A)                                                               │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [K] physical NIC RX → OVS/bridge → vnet TX                                 │   │
  │  │      (icmp_drop_detector RepInternal: phy→vnet on send-host)                │   │
  │  │                                                                              │   │
  │  │  [L] tun_net_xmit → vhost_signal → eventfd → irqfd → KVM IRQ injection      │   │
  │  │      (tun_tx_to_kvm_irq: S1→S5, receiving reply)                            │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                              │                                                      │
  │                              ▼                                                      │
  │  Sender VM (VM-A)                                                                   │
  │  ┌──────────────────────────────────────────────────────────────────────────────┐   │
  │  │  [M] virtio-net RX → tcp/ip stack → icmp_rcv (reply)                        │   │
  │  │      (kernel_icmp_rtt Path 2)                                                │   │
  │  └──────────────────────────────────────────────────────────────────────────────┘   │
  │                                                                                     │
  └─────────────────────────────────────────────────────────────────────────────────────┘
```

## Segment Definitions

| Segment | Description | Direction | Location | Measurable |
|---------|-------------|-----------|----------|------------|
| A | Sender VM kernel TX stack (icmp_send → virtio TX) | Request | Sender VM | Yes |
| B | Sender host internal forwarding (vnet RX → phy TX) | Request | Sender Host | Yes |
| B_1 | Sender host KVM→TUN (ioeventfd → handle_tx_kick → tun_sendmsg → netif) | Request | Sender Host | Yes |
| C | Network transit - request direction | Request | Wire | Derived |
| D | Receiver host internal forwarding (phy RX → vnet TX) | Request | Receiver Host | Yes |
| E | Receiver host vhost→KVM IRQ injection | Request | Receiver Host | Yes |
| F | Receiver VM kernel RX stack (virtio RX → icmp_rcv) | Request | Receiver VM | Yes |
| G | Receiver VM ICMP echo processing | - | Receiver VM | Yes |
| H | Receiver VM kernel TX stack (icmp_reply → virtio TX) | Reply | Receiver VM | Yes |
| I | Receiver host internal forwarding (vnet RX → phy TX) | Reply | Receiver Host | Yes |
| I_1 | Receiver host KVM→TUN (ioeventfd → handle_tx_kick → tun_sendmsg → netif) | Reply | Receiver Host | Yes |
| J | Network transit - reply direction | Reply | Wire | Derived |
| K | Sender host internal forwarding (phy RX → vnet TX) | Reply | Sender Host | Yes |
| L | Sender host vhost→KVM IRQ injection | Reply | Sender Host | Yes |
| M | Sender VM kernel RX stack (virtio RX → icmp_rcv) | Reply | Sender VM | Yes |

## Layer Grouping

| Layer | Segments | Description |
|-------|----------|-------------|
| VM Internal | A, F, G, H, M | Guest kernel network stack |
| Host Internal | B, D, I, K | Host OVS/bridge forwarding |
| Physical Network | C, J | Wire and switch latency |
| Virtualization RX (tun→KVM) | E, L | vhost→KVM IRQ injection path |
| Virtualization TX (KVM→tun) | B_1, I_1 | KVM ioeventfd→vhost→TUN path |

## Notes

1. **Segments C and J** (physical network) cannot be directly measured and must be derived from other measurements.

2. **Segments E and L** (vhost→KVM, VM RX path) are measured by `tun_tx_to_kvm_irq.py` which traces 5 stages:
   - Stage 1 (S1): tun_net_xmit
   - Stage 2 (S2): vhost_signal_used_irq
   - Stage 3 (S3): eventfd_signal
   - Stage 4 (S4): irqfd_wakeup
   - Stage 5 (S5): kvm_set_irq (KVM IRQ injection)

3. **Segments B_1 and I_1** (KVM→TUN, VM TX path) are measured by `kvm_vhost_tun_latency_details.py` which traces 3 stages:
   - Stage 0 (S0): ioeventfd_write → handle_tx_kick (KVM notifies vhost worker)
   - Stage 1 (S1): handle_tx_kick → tun_sendmsg (vhost worker processes TX)
   - Stage 2 (S2): tun_sendmsg → netif_receive_skb (TUN device sends packet)

4. **Virtualization layer now fully measured**: With both `tun_tx_to_kvm_irq.py` (RX) and `kvm_vhost_tun_latency_details.py` (TX), the virtualization layer is nearly completely measurable. The key latency contributor is typically the vhost worker wakeup delay (S1→S2 in RX path, S0 in TX path), often caused by CPU C-state transitions.
