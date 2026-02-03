#!/bin/bash
# Start icmp_path_tracer on hosts monitoring vnet↔phy boundaries for VM traffic.
#
# Sender Host: rx=vnet (from VM), tx=phy (to network)
# Receiver Host: rx=phy (from network), tx=vnet (to VM)

set -e

RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}
TIMEOUT_MS=${TIMEOUT_MS:-1000}

for VAR in SENDER_HOST_SSH SENDER_VM_IP RECEIVER_VM_IP SEND_VNET_IF SENDER_PHY_IF RECEIVER_HOST_SSH RECV_VNET_IF RECEIVER_PHY_IF DURATION MEASUREMENT_DIR; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

mkdir -p "${MEASUREMENT_DIR}"
CMDLOG="${MEASUREMENT_DIR}/commands.log"

echo "=== VM Network Drop Measurement ===" >> "${CMDLOG}"
echo "Timestamp: $(date)" >> "${CMDLOG}"
echo "Sender Host: ${SENDER_HOST_SSH} vnet=${SEND_VNET_IF} phy=${SENDER_PHY_IF}" >> "${CMDLOG}"
echo "Receiver Host: ${RECEIVER_HOST_SSH} phy=${RECEIVER_PHY_IF} vnet=${RECV_VNET_IF}" >> "${CMDLOG}"
echo "VM IPs: ${SENDER_VM_IP} -> ${RECEIVER_VM_IP}" >> "${CMDLOG}"
echo "" >> "${CMDLOG}"

declare -a SSH_PIDS=()

# [1/2] Receiver Host first: rx=phy (from network), tx=vnet (to VM)
RECV_CMD="sudo python3 /tmp/icmp_path_tracer.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${RECEIVER_PHY_IF} --tx-iface ${RECV_VNET_IF} --timeout-ms ${TIMEOUT_MS} --verbose"
echo "[1/2] receiver-host (phy→vnet): ${RECV_CMD}"
echo "[1/2] receiver-host: ssh ${RECEIVER_HOST_SSH} '${RECV_CMD}'" >> "${CMDLOG}"
ssh "${RECEIVER_HOST_SSH}" "${RECV_CMD}" > "${MEASUREMENT_DIR}/receiver-host.log" 2>&1 &
SSH_PIDS+=($!)

sleep "${RECEIVER_WARMUP}"

# [2/2] Sender Host: rx=vnet (from VM), tx=phy (to network)
SEND_CMD="sudo python3 /tmp/icmp_path_tracer.py --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} --rx-iface ${SEND_VNET_IF} --tx-iface ${SENDER_PHY_IF} --timeout-ms ${TIMEOUT_MS} --verbose"
echo "[2/2] sender-host (vnet→phy): ${SEND_CMD}"
echo "[2/2] sender-host: ssh ${SENDER_HOST_SSH} '${SEND_CMD}'" >> "${CMDLOG}"
ssh "${SENDER_HOST_SSH}" "${SEND_CMD}" > "${MEASUREMENT_DIR}/sender-host.log" 2>&1 &
SSH_PIDS+=($!)

echo ""
echo "Both tools started. Measuring for ${DURATION}s..."
sleep "${DURATION}"

echo ""
echo "Stopping tools (SIGINT on remote hosts)..."
ssh "${SENDER_HOST_SSH}" "sudo pkill -INT -f icmp_path_tracer.py" 2>/dev/null || true
ssh "${RECEIVER_HOST_SSH}" "sudo pkill -INT -f icmp_path_tracer.py" 2>/dev/null || true

echo "Waiting ${SHUTDOWN_WAIT}s for graceful shutdown..."
sleep "${SHUTDOWN_WAIT}"

# Wait for SSH processes to exit (they should exit after remote tools are killed)
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

echo ""
echo "Log files:"
for LOG in sender-host.log receiver-host.log; do
    LOGPATH="${MEASUREMENT_DIR}/${LOG}"
    if [ -f "${LOGPATH}" ] && [ -s "${LOGPATH}" ]; then
        LINES=$(wc -l < "${LOGPATH}")
        echo "  ${LOG}: ${LINES} lines"
    else
        echo "  ${LOG}: EMPTY or MISSING"
    fi
done

echo "Measurement complete."
