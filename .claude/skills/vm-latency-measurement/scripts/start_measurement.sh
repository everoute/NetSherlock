#!/bin/bash
# Start 8 BPF measurement tools with receiver-first timing.
#
# CRITICAL: Receiver-side tools must start BEFORE sender-side tools
# to ensure no packets are missed.
#
# Required environment variables:
#   SENDER_VM_SSH, SENDER_VM_IP, SENDER_HOST_SSH
#   SEND_VNET_IF, SEND_PHY_IF, SEND_VM_IF
#   RECEIVER_VM_SSH, RECEIVER_VM_IP, RECEIVER_HOST_SSH
#   RECV_VNET_IF, RECV_PHY_IF, RECV_VM_IF
#   DURATION, MEASUREMENT_DIR
#
# Optional environment variables (with defaults):
#   RECEIVER_WARMUP (default: 2)
#   SHUTDOWN_WAIT (default: 3)
#
# Note: Traffic generation is handled by measure.py, not this script.
#
# The 8 measurement tools:
#   Sender side:
#     1. sender-vm: kernel_icmp_rtt.py (Segments A, M)
#     2. sender-host: icmp_drop_detector.py (Segments B, K)
#     3. sender-host: kvm_vhost_tun_latency_details.py (Segment B_1)
#     4. sender-host: tun_tx_to_kvm_irq.py (Segment L)
#   Receiver side:
#     5. receiver-vm: kernel_icmp_rtt.py (Segments F, G, H)
#     6. receiver-host: icmp_drop_detector.py (Segments D, I)
#     7. receiver-host: kvm_vhost_tun_latency_details.py (Segment I_1)
#     8. receiver-host: tun_tx_to_kvm_irq.py (Segment E)

set -e

# Default values for timing parameters
RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}

# Check required variables
REQUIRED_VARS=(
    SENDER_VM_SSH SENDER_VM_IP SENDER_HOST_SSH
    SEND_VNET_IF SEND_PHY_IF SEND_VM_IF
    RECEIVER_VM_SSH RECEIVER_VM_IP RECEIVER_HOST_SSH
    RECV_VNET_IF RECV_PHY_IF RECV_VM_IF
    DURATION
    MEASUREMENT_DIR
)

for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

# Ensure measurement directory exists
mkdir -p "${MEASUREMENT_DIR}"
CMDLOG="${MEASUREMENT_DIR}/commands.log"

# Append to existing commands.log
echo "" >> ${CMDLOG}
echo "=== Starting 8 Measurement Tools ===" >> ${CMDLOG}
echo "Timestamp: $(date)" >> ${CMDLOG}
echo "DURATION=${DURATION}s, INLINE_DISCOVER=${INLINE_DISCOVER_DURATION}s, RECEIVER_WARMUP=${RECEIVER_WARMUP}s, SHUTDOWN_WAIT=${SHUTDOWN_WAIT}s" >> ${CMDLOG}
echo "" >> ${CMDLOG}

########################################
# Start ALL 8 tools in parallel (no receiver-first, all simultaneous)
# kvm_vhost_tun_latency: discover + measure in SINGLE SSH session
# to avoid vhost queue drift between separate SSH connections
########################################
echo ""
echo "=== Starting ALL 8 measurement tools in parallel ==="

# Discovery duration for inline discover (shorter since it's per-tool)
INLINE_DISCOVER_DURATION=${INLINE_DISCOVER_DURATION:-15}

# [1/8] Receiver Host - kvm_vhost_tun_latency (discover + measure in single SSH)
echo "[1/8] recv-host: kvm_vhost_tun_latency (inline discover + measure)"
# Combine discover and measure in one SSH command to avoid queue drift
CMD="sudo python3 /tmp/kvm_vhost_tun_latency_details.py --mode discover --device ${RECV_VNET_IF} --flow 'proto=icmp,src=${RECEIVER_VM_IP},dst=${SENDER_VM_IP}' --duration ${INLINE_DISCOVER_DURATION} --out /tmp/kvm-tun-recv-profile.json && sudo python3 /tmp/kvm_vhost_tun_latency_details.py --mode measure --profile /tmp/kvm-tun-recv-profile.json"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-kvm-tun.log 2>&1 &
echo "      PID: $!, LOG: recv-host-kvm-tun.log" >> ${CMDLOG}

# [2/8] Sender Host - kvm_vhost_tun_latency (discover + measure in single SSH)
echo "[2/8] send-host: kvm_vhost_tun_latency (inline discover + measure)"
CMD="sudo python3 /tmp/kvm_vhost_tun_latency_details.py --mode discover --device ${SEND_VNET_IF} --flow 'proto=icmp,src=${SENDER_VM_IP},dst=${RECEIVER_VM_IP}' --duration ${INLINE_DISCOVER_DURATION} --out /tmp/kvm-tun-send-profile.json && sudo python3 /tmp/kvm_vhost_tun_latency_details.py --mode measure --profile /tmp/kvm-tun-send-profile.json"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-kvm-tun.log 2>&1 &
echo "      PID: $!, LOG: send-host-kvm-tun.log" >> ${CMDLOG}

# [3/8] Receiver Host - icmp_drop_detector
echo "[3/8] recv-host: icmp_drop_detector"
CMD="sudo python3 /tmp/icmp_drop_detector.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${RECV_PHY_IF} --tx-iface ${RECV_VNET_IF} --verbose"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-icmp.log 2>&1 &
echo "      PID: $!, LOG: recv-host-icmp.log" >> ${CMDLOG}

# [4/8] Sender Host - icmp_drop_detector
echo "[4/8] send-host: icmp_drop_detector"
CMD="sudo python3 /tmp/icmp_drop_detector.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${SEND_VNET_IF} --tx-iface ${SEND_PHY_IF} --verbose"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-icmp.log 2>&1 &
echo "      PID: $!, LOG: send-host-icmp.log" >> ${CMDLOG}

# [5/8] Receiver Host - tun_tx_to_kvm_irq
echo "[5/8] recv-host: tun_tx_to_kvm_irq"
CMD="sudo python3 /tmp/tun_tx_to_kvm_irq.py --device ${RECV_VNET_IF} --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --protocol icmp"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-vhost-rx.log 2>&1 &
echo "      PID: $!, LOG: recv-host-vhost-rx.log" >> ${CMDLOG}

# [6/8] Sender Host - tun_tx_to_kvm_irq
echo "[6/8] send-host: tun_tx_to_kvm_irq"
CMD="sudo python3 /tmp/tun_tx_to_kvm_irq.py --device ${SEND_VNET_IF} --src-ip ${RECEIVER_VM_IP} --dst-ip ${SENDER_VM_IP} --protocol icmp"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-vhost-rx.log 2>&1 &
echo "      PID: $!, LOG: send-host-vhost-rx.log" >> ${CMDLOG}

# [7/8] Receiver VM - kernel_icmp_rtt
echo "[7/8] recv-vm: kernel_icmp_rtt (interface=${RECV_VM_IF})"
CMD="sudo python3 /tmp/kernel_icmp_rtt.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --interface ${RECV_VM_IF} --direction rx --disable-kernel-stacks"
echo "      CMD: ssh ${RECEIVER_VM_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_VM_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-vm-icmp.log 2>&1 &
echo "      PID: $!, LOG: recv-vm-icmp.log" >> ${CMDLOG}

# [8/8] Sender VM - kernel_icmp_rtt
echo "[8/8] send-vm: kernel_icmp_rtt (interface=${SEND_VM_IF})"
CMD="sudo python3 /tmp/kernel_icmp_rtt.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --interface ${SEND_VM_IF} --direction tx --disable-kernel-stacks"
echo "      CMD: ssh ${SENDER_VM_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_VM_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-vm-icmp.log 2>&1 &
echo "      PID: $!, LOG: send-vm-icmp.log" >> ${CMDLOG}

echo ""
echo "=== All 8 tools started ==="

echo "" >> ${CMDLOG}
echo "=== All 8 tools started ===" >> ${CMDLOG}

########################################
# Wait for measurement duration
# Total wait = INLINE_DISCOVER_DURATION + DURATION
# - kvm_vhost_tun_latency tools need INLINE_DISCOVER_DURATION for discover
# - Then DURATION for actual measurement
########################################
TOTAL_WAIT=$((INLINE_DISCOVER_DURATION + DURATION))
echo ""
echo "=== Waiting ${TOTAL_WAIT}s (${INLINE_DISCOVER_DURATION}s discover + ${DURATION}s measure) ==="
echo "=== Measurement Duration ===" >> ${CMDLOG}
echo "Waiting ${TOTAL_WAIT}s (${INLINE_DISCOVER_DURATION}s discover + ${DURATION}s measure)..." >> ${CMDLOG}
sleep ${TOTAL_WAIT}

########################################
# Stop Tools
########################################
echo ""
echo "=== Stopping measurement tools ==="
echo "=== Stopping Tools ===" >> ${CMDLOG}

# Stop tools gracefully (SIGINT)
ssh ${SENDER_VM_SSH} "pkill -INT -f kernel_icmp_rtt.py" 2>/dev/null || true
ssh ${RECEIVER_VM_SSH} "pkill -INT -f kernel_icmp_rtt.py" 2>/dev/null || true
ssh ${SENDER_HOST_SSH} "pkill -INT -f 'icmp_drop_detector.py|tun_tx_to_kvm_irq.py|kvm_vhost_tun_latency'" 2>/dev/null || true
ssh ${RECEIVER_HOST_SSH} "pkill -INT -f 'icmp_drop_detector.py|tun_tx_to_kvm_irq.py|kvm_vhost_tun_latency'" 2>/dev/null || true

echo "Waiting ${SHUTDOWN_WAIT}s for graceful shutdown..."
sleep ${SHUTDOWN_WAIT}

########################################
# Verify Logs
########################################
echo ""
echo "=== Verifying collected logs ==="
echo "" >> ${CMDLOG}
echo "=== Log Verification ===" >> ${CMDLOG}

LOGS=(
    "send-vm-icmp.log"
    "recv-vm-icmp.log"
    "send-host-icmp.log"
    "recv-host-icmp.log"
    "send-host-vhost-rx.log"
    "recv-host-vhost-rx.log"
    "send-host-kvm-tun.log"
    "recv-host-kvm-tun.log"
)

ALL_OK=true
for LOG in "${LOGS[@]}"; do
    LOGFILE="${MEASUREMENT_DIR}/${LOG}"
    if [ -f "${LOGFILE}" ]; then
        LINES=$(wc -l < "${LOGFILE}")
        SIZE=$(wc -c < "${LOGFILE}")
        echo "  ${LOG}: ${LINES} lines, ${SIZE} bytes" | tee -a ${CMDLOG}
    else
        echo "  WARNING: ${LOG} not found!" | tee -a ${CMDLOG}
        ALL_OK=false
    fi
done

echo ""
if [ "${ALL_OK}" = true ]; then
    echo "Measurement complete. All 8 logs collected."
else
    echo "Warning: Some logs are missing. Check commands.log for details."
fi

echo "" >> ${CMDLOG}
echo "=== Measurement Complete ===" >> ${CMDLOG}
echo "Timestamp: $(date)" >> ${CMDLOG}
