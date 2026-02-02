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
#     2. sender-host: icmp_path_tracer.py (Segments B, K)
#     3. sender-host: kvm_vhost_tun_latency_no_discovery.py (Segment B_1)
#     4. sender-host: tun_tx_to_kvm_irq.py (Segment L)
#   Receiver side:
#     5. receiver-vm: kernel_icmp_rtt.py (Segments F, G, H)
#     6. receiver-host: icmp_path_tracer.py (Segments D, I)
#     7. receiver-host: kvm_vhost_tun_latency_no_discovery.py (Segment I_1)
#     8. receiver-host: tun_tx_to_kvm_irq.py (Segment E)

set -e

# Default values for timing parameters
RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}

# Array to track SSH background process PIDs
declare -a SSH_PIDS=()

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
echo "DURATION=${DURATION}s, RECEIVER_WARMUP=${RECEIVER_WARMUP}s, SHUTDOWN_WAIT=${SHUTDOWN_WAIT}s" >> ${CMDLOG}
echo "" >> ${CMDLOG}

########################################
# Start ALL 8 tools in parallel
# kvm_vhost_tun_latency_no_discovery: no discover phase needed,
# auto-detects QEMU PID and vhost threads at startup
########################################
echo ""
echo "=== Starting ALL 8 measurement tools in parallel ==="

# [1/8] Receiver Host - kvm_vhost_tun_latency (no discovery needed)
echo "[1/8] recv-host: kvm_vhost_tun_latency_no_discovery"
# New tool auto-detects QEMU PID and vhost threads, no discovery phase needed
CMD="sudo python3 /tmp/kvm_vhost_tun_latency_no_discovery.py --device ${RECV_VNET_IF} --flow 'proto=icmp,src=${RECEIVER_VM_IP},dst=${SENDER_VM_IP}'"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-kvm-tun.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: recv-host-kvm-tun.log" >> ${CMDLOG}

# [2/8] Sender Host - kvm_vhost_tun_latency (no discovery needed)
echo "[2/8] send-host: kvm_vhost_tun_latency_no_discovery"
CMD="sudo python3 /tmp/kvm_vhost_tun_latency_no_discovery.py --device ${SEND_VNET_IF} --flow 'proto=icmp,src=${SENDER_VM_IP},dst=${RECEIVER_VM_IP}'"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-kvm-tun.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: send-host-kvm-tun.log" >> ${CMDLOG}

# [3/8] Receiver Host - icmp_path_tracer
echo "[3/8] recv-host: icmp_path_tracer"
CMD="sudo python3 /tmp/icmp_path_tracer.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${RECV_PHY_IF} --tx-iface ${RECV_VNET_IF} --verbose"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-icmp.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: recv-host-icmp.log" >> ${CMDLOG}

# [4/8] Sender Host - icmp_path_tracer
echo "[4/8] send-host: icmp_path_tracer"
CMD="sudo python3 /tmp/icmp_path_tracer.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${SEND_VNET_IF} --tx-iface ${SEND_PHY_IF} --verbose"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-icmp.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: send-host-icmp.log" >> ${CMDLOG}

# [5/8] Receiver Host - tun_tx_to_kvm_irq
echo "[5/8] recv-host: tun_tx_to_kvm_irq"
CMD="sudo python3 /tmp/tun_tx_to_kvm_irq.py --device ${RECV_VNET_IF} --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --protocol icmp"
echo "      CMD: ssh ${RECEIVER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-host-vhost-rx.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: recv-host-vhost-rx.log" >> ${CMDLOG}

# [6/8] Sender Host - tun_tx_to_kvm_irq
echo "[6/8] send-host: tun_tx_to_kvm_irq"
CMD="sudo python3 /tmp/tun_tx_to_kvm_irq.py --device ${SEND_VNET_IF} --src-ip ${RECEIVER_VM_IP} --dst-ip ${SENDER_VM_IP} --protocol icmp"
echo "      CMD: ssh ${SENDER_HOST_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_HOST_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-host-vhost-rx.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: send-host-vhost-rx.log" >> ${CMDLOG}

# [7/8] Receiver VM - kernel_icmp_rtt
echo "[7/8] recv-vm: kernel_icmp_rtt (interface=${RECV_VM_IF})"
CMD="sudo python3 /tmp/kernel_icmp_rtt.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --interface ${RECV_VM_IF} --direction rx --disable-kernel-stacks"
echo "      CMD: ssh ${RECEIVER_VM_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${RECEIVER_VM_SSH} "${CMD}" > ${MEASUREMENT_DIR}/recv-vm-icmp.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: recv-vm-icmp.log" >> ${CMDLOG}

# [8/8] Sender VM - kernel_icmp_rtt
echo "[8/8] send-vm: kernel_icmp_rtt (interface=${SEND_VM_IF})"
CMD="sudo python3 /tmp/kernel_icmp_rtt.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --interface ${SEND_VM_IF} --direction tx --disable-kernel-stacks"
echo "      CMD: ssh ${SENDER_VM_SSH} '${CMD}'" | tee -a ${CMDLOG}
ssh ${SENDER_VM_SSH} "${CMD}" > ${MEASUREMENT_DIR}/send-vm-icmp.log 2>&1 &
PID_TMP=$!
SSH_PIDS+=($PID_TMP)
echo "      PID: $PID_TMP, LOG: send-vm-icmp.log" >> ${CMDLOG}

echo ""
echo "=== All 8 tools started ==="

echo "" >> ${CMDLOG}
echo "=== All 8 tools started ===" >> ${CMDLOG}

########################################
# Wait for measurement duration
# No discovery phase needed with kvm_vhost_tun_latency_no_discovery.py
########################################
echo ""
echo "=== Waiting ${DURATION}s for measurement ==="
echo "=== Measurement Duration ===" >> ${CMDLOG}
echo "Waiting ${DURATION}s for measurement..." >> ${CMDLOG}
sleep ${DURATION}

########################################
# Stop Tools
########################################
echo ""
echo "=== Stopping measurement tools ==="
echo "=== Stopping Tools ===" >> ${CMDLOG}

# Stop tools gracefully (SIGINT) on remote hosts
# Note: BPF tools run as root via sudo, so we need sudo for pkill
ssh ${SENDER_VM_SSH} "sudo pkill -INT -f kernel_icmp_rtt.py" 2>/dev/null || true
ssh ${RECEIVER_VM_SSH} "sudo pkill -INT -f kernel_icmp_rtt.py" 2>/dev/null || true
ssh ${SENDER_HOST_SSH} "sudo pkill -INT -f icmp_path_tracer.py; sudo pkill -INT -f tun_tx_to_kvm_irq.py; sudo pkill -INT -f kvm_vhost_tun_latency" 2>/dev/null || true
ssh ${RECEIVER_HOST_SSH} "sudo pkill -INT -f icmp_path_tracer.py; sudo pkill -INT -f tun_tx_to_kvm_irq.py; sudo pkill -INT -f kvm_vhost_tun_latency" 2>/dev/null || true

echo "Waiting ${SHUTDOWN_WAIT}s for graceful shutdown..."
sleep ${SHUTDOWN_WAIT}

# Wait for SSH processes to exit with timeout (they should exit after remote tools are killed)
echo "Waiting for SSH processes to flush output (max 10s)..."
WAIT_COUNT=0
MAX_WAIT=10
while [ ${WAIT_COUNT} -lt ${MAX_WAIT} ]; do
    ALL_DONE=true
    for PID in "${SSH_PIDS[@]}"; do
        if kill -0 ${PID} 2>/dev/null; then
            ALL_DONE=false
            break
        fi
    done
    if [ "${ALL_DONE}" = true ]; then
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

# If any SSH processes are still running, terminate them
for PID in "${SSH_PIDS[@]}"; do
    if kill -0 ${PID} 2>/dev/null; then
        echo "  Terminating SSH PID ${PID}..."
        kill ${PID} 2>/dev/null || true
    fi
done
sleep 1
echo "All SSH processes completed."

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
