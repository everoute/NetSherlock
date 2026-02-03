#!/bin/bash
# Start system_icmp_path_tracer on both hosts.
#
# Receiver Host (primary): traces A→B traffic (--src-ip=A, --dst-ip=B)
# Sender Host (secondary): traces B→A traffic (--src-ip=B, --dst-ip=A)
#
# Receiver starts first to avoid missing early packets.

set -e

RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}
TIMEOUT_MS=${TIMEOUT_MS:-1000}

for VAR in SENDER_HOST_SSH SENDER_IP SENDER_PHY_IF RECEIVER_HOST_SSH RECEIVER_IP RECEIVER_PHY_IF DURATION MEASUREMENT_DIR; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

mkdir -p "${MEASUREMENT_DIR}"
CMDLOG="${MEASUREMENT_DIR}/commands.log"

echo "=== System Network Packet Drop & Latency Measurement ===" >> "${CMDLOG}"
echo "Timestamp: $(date)" >> "${CMDLOG}"
echo "Sender: ${SENDER_HOST_SSH} (${SENDER_IP}) IF=${SENDER_PHY_IF}" >> "${CMDLOG}"
echo "Receiver: ${RECEIVER_HOST_SSH} (${RECEIVER_IP}) IF=${RECEIVER_PHY_IF}" >> "${CMDLOG}"
echo "DURATION=${DURATION}s, TIMEOUT=${TIMEOUT_MS}ms" >> "${CMDLOG}"
echo "" >> "${CMDLOG}"

declare -a SSH_PIDS=()

# [1/2] Receiver Host (primary): traces traffic from Sender → Receiver
RECV_CMD="sudo python3 /tmp/system_icmp_path_tracer.py --src-ip ${SENDER_IP} --dst-ip ${RECEIVER_IP} --phy-iface ${RECEIVER_PHY_IF} --timeout-ms ${TIMEOUT_MS} --verbose"
echo "[1/2] receiver-host (primary, traces ${SENDER_IP}→${RECEIVER_IP}):"
echo "  ${RECV_CMD}"
echo "[1/2] receiver-host: ssh ${RECEIVER_HOST_SSH} '${RECV_CMD}'" >> "${CMDLOG}"
ssh "${RECEIVER_HOST_SSH}" "${RECV_CMD}" > "${MEASUREMENT_DIR}/receiver-host.log" 2>&1 &
SSH_PIDS+=($!)

sleep "${RECEIVER_WARMUP}"

# [2/2] Sender Host (secondary): traces traffic from Receiver → Sender
SEND_CMD="sudo python3 /tmp/system_icmp_path_tracer.py --src-ip ${RECEIVER_IP} --dst-ip ${SENDER_IP} --phy-iface ${SENDER_PHY_IF} --timeout-ms ${TIMEOUT_MS} --verbose"
echo "[2/2] sender-host (secondary, traces ${RECEIVER_IP}→${SENDER_IP}):"
echo "  ${SEND_CMD}"
echo "[2/2] sender-host: ssh ${SENDER_HOST_SSH} '${SEND_CMD}'" >> "${CMDLOG}"
ssh "${SENDER_HOST_SSH}" "${SEND_CMD}" > "${MEASUREMENT_DIR}/sender-host.log" 2>&1 &
SSH_PIDS+=($!)

echo ""
echo "Both tools started. Measuring for ${DURATION}s..."
sleep "${DURATION}"

echo ""
echo "Stopping tools (SIGINT)..."
for PID in "${SSH_PIDS[@]}"; do
    kill -INT "${PID}" 2>/dev/null || true
done

echo "Waiting ${SHUTDOWN_WAIT}s for graceful shutdown..."
sleep "${SHUTDOWN_WAIT}"

for PID in "${SSH_PIDS[@]}"; do
    kill -9 "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
done

echo ""
echo "Log files:"
for LOG in receiver-host.log sender-host.log; do
    LOGPATH="${MEASUREMENT_DIR}/${LOG}"
    if [ -f "${LOGPATH}" ] && [ -s "${LOGPATH}" ]; then
        LINES=$(wc -l < "${LOGPATH}")
        echo "  ${LOG}: ${LINES} lines"
    else
        echo "  ${LOG}: EMPTY or MISSING"
    fi
done

echo ""
echo "Measurement complete."
