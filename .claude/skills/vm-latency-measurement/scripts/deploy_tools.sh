#!/bin/bash
# Deploy BPF measurement tools to target machines.
#
# Required environment variables:
#   SENDER_VM_SSH, SENDER_HOST_SSH, RECEIVER_VM_SSH, RECEIVER_HOST_SSH
#   LOCAL_TOOLS - path to local BPF tools directory
#
# Tool paths (relative to LOCAL_TOOLS):
#   - kernel_icmp_rtt.py: performance/system-network/
#   - icmp_drop_detector.py: linux-network-stack/packet-drop/
#   - tun_tx_to_kvm_irq.py: kvm-virt-network/tun/
#   - kvm_vhost_tun_latency_no_discovery.py: kvm-virt-network/vhost-net/

set -e

echo "Deploying BPF tools..."
echo "Source: ${LOCAL_TOOLS}"

# Check required variables
for VAR in SENDER_VM_SSH SENDER_HOST_SSH RECEIVER_VM_SSH RECEIVER_HOST_SSH LOCAL_TOOLS; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

# Tool paths
KERNEL_ICMP_RTT="${LOCAL_TOOLS}/performance/system-network/kernel_icmp_rtt.py"
ICMP_DROP_DETECTOR="${LOCAL_TOOLS}/linux-network-stack/packet-drop/icmp_drop_detector.py"
TUN_TX_TO_KVM_IRQ="${LOCAL_TOOLS}/kvm-virt-network/tun/tun_tx_to_kvm_irq.py"
KVM_VHOST_TUN_LATENCY="${LOCAL_TOOLS}/kvm-virt-network/vhost-net/kvm_vhost_tun_latency_no_discovery.py"

# Verify tools exist
for TOOL in "${KERNEL_ICMP_RTT}" "${ICMP_DROP_DETECTOR}" "${TUN_TX_TO_KVM_IRQ}" "${KVM_VHOST_TUN_LATENCY}"; do
    if [ ! -f "${TOOL}" ]; then
        echo "Error: Tool not found: ${TOOL}" >&2
        exit 1
    fi
done

echo ""
echo "[1/4] Deploying to Sender VM (${SENDER_VM_SSH})..."
scp -q "${KERNEL_ICMP_RTT}" "${SENDER_VM_SSH}:/tmp/"
echo "  - kernel_icmp_rtt.py -> /tmp/"

echo ""
echo "[2/4] Deploying to Receiver VM (${RECEIVER_VM_SSH})..."
scp -q "${KERNEL_ICMP_RTT}" "${RECEIVER_VM_SSH}:/tmp/"
echo "  - kernel_icmp_rtt.py -> /tmp/"

echo ""
echo "[3/4] Deploying to Sender Host (${SENDER_HOST_SSH})..."
scp -q "${ICMP_DROP_DETECTOR}" "${SENDER_HOST_SSH}:/tmp/"
scp -q "${TUN_TX_TO_KVM_IRQ}" "${SENDER_HOST_SSH}:/tmp/"
scp -q "${KVM_VHOST_TUN_LATENCY}" "${SENDER_HOST_SSH}:/tmp/"
echo "  - icmp_drop_detector.py -> /tmp/"
echo "  - tun_tx_to_kvm_irq.py -> /tmp/"
echo "  - kvm_vhost_tun_latency_no_discovery.py -> /tmp/"

echo ""
echo "[4/4] Deploying to Receiver Host (${RECEIVER_HOST_SSH})..."
scp -q "${ICMP_DROP_DETECTOR}" "${RECEIVER_HOST_SSH}:/tmp/"
scp -q "${TUN_TX_TO_KVM_IRQ}" "${RECEIVER_HOST_SSH}:/tmp/"
scp -q "${KVM_VHOST_TUN_LATENCY}" "${RECEIVER_HOST_SSH}:/tmp/"
echo "  - icmp_drop_detector.py -> /tmp/"
echo "  - tun_tx_to_kvm_irq.py -> /tmp/"
echo "  - kvm_vhost_tun_latency_no_discovery.py -> /tmp/"

echo ""
echo "Tool deployment complete."
