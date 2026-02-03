#!/bin/bash
# Start *_path_tracer on hosts monitoring vnet↔phy boundaries for VM traffic (v2).
#
# Supports multi-protocol (ICMP MVP, TCP/UDP reserved) with configurable:
#   - OUTPUT_MODE: verbose (default) or stats
#   - PORT: port filter for TCP/UDP
#   - FOCUS: drop (default) or latency
#
# Sender Host: rx=vnet (from VM), tx=phy (to network)
# Receiver Host: rx=phy (from network), tx=vnet (to VM)

set -e

# v2: Protocol and mode parameters (from measure.py env)
PROTOCOL=${PROTOCOL:-icmp}
FOCUS=${FOCUS:-drop}
OUTPUT_MODE=${OUTPUT_MODE:-verbose}
TOOL_NAME=${TOOL_NAME:-icmp_path_tracer.py}

RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}
TIMEOUT_MS=${TIMEOUT_MS:-1000}

# v2: Optional TCP/UDP parameters
PORT=${PORT:-}
STATS_INTERVAL=${STATS_INTERVAL:-5}

for VAR in SENDER_HOST_SSH SENDER_VM_IP RECEIVER_VM_IP SEND_VNET_IF SENDER_PHY_IF RECEIVER_HOST_SSH RECV_VNET_IF RECEIVER_PHY_IF DURATION MEASUREMENT_DIR; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

mkdir -p "${MEASUREMENT_DIR}"
CMDLOG="${MEASUREMENT_DIR}/commands.log"

# Build tool-specific arguments for VM boundary tools
build_tool_args() {
    local role=$1  # sender or receiver
    local args="--src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP}"

    # Set interfaces based on role (VM boundary monitoring)
    if [ "$role" = "sender" ]; then
        # Sender: rx=vnet (from VM), tx=phy (to network)
        args="${args} --rx-iface ${SEND_VNET_IF} --tx-iface ${SENDER_PHY_IF}"
    else
        # Receiver: rx=phy (from network), tx=vnet (to VM)
        args="${args} --rx-iface ${RECEIVER_PHY_IF} --tx-iface ${RECV_VNET_IF}"
    fi

    # Add timeout
    args="${args} --timeout-ms ${TIMEOUT_MS}"

    # Protocol-specific options
    case ${PROTOCOL} in
        icmp)
            if [ "${OUTPUT_MODE}" = "verbose" ]; then
                args="${args} --verbose"
            fi
            ;;
        tcp|udp)
            if [ -n "${PORT}" ]; then
                args="${args} --port ${PORT}"
            fi
            if [ "${OUTPUT_MODE}" = "stats" ]; then
                args="${args} --stats-interval ${STATS_INTERVAL}"
            else
                args="${args} --verbose"
            fi
            ;;
    esac

    echo "${args}"
}

echo "=== VM Network Path Tracer Measurement (v2) ===" >> "${CMDLOG}"
echo "Timestamp: $(date)" >> "${CMDLOG}"
echo "Sender Host: ${SENDER_HOST_SSH} vnet=${SEND_VNET_IF} phy=${SENDER_PHY_IF}" >> "${CMDLOG}"
echo "Receiver Host: ${RECEIVER_HOST_SSH} phy=${RECEIVER_PHY_IF} vnet=${RECV_VNET_IF}" >> "${CMDLOG}"
echo "VM IPs: ${SENDER_VM_IP} -> ${RECEIVER_VM_IP}" >> "${CMDLOG}"
echo "Protocol=${PROTOCOL}, Focus=${FOCUS}, OutputMode=${OUTPUT_MODE}" >> "${CMDLOG}"
echo "" >> "${CMDLOG}"

declare -a SSH_PIDS=()

# [1/2] Receiver Host first: rx=phy (from network), tx=vnet (to VM)
RECV_ARGS=$(build_tool_args "receiver")
RECV_CMD="sudo python3 /tmp/${TOOL_NAME} ${RECV_ARGS}"
echo "[1/2] receiver-host (phy→vnet):"
echo "  Protocol: ${PROTOCOL}"
echo "  ${RECV_CMD}"
echo "[1/2] receiver-host: ssh ${RECEIVER_HOST_SSH} '${RECV_CMD}'" >> "${CMDLOG}"
ssh "${RECEIVER_HOST_SSH}" "${RECV_CMD}" > "${MEASUREMENT_DIR}/receiver-host.log" 2>&1 &
SSH_PIDS+=($!)

sleep "${RECEIVER_WARMUP}"

# [2/2] Sender Host: rx=vnet (from VM), tx=phy (to network)
SEND_ARGS=$(build_tool_args "sender")
SEND_CMD="sudo python3 /tmp/${TOOL_NAME} ${SEND_ARGS}"
echo "[2/2] sender-host (vnet→phy):"
echo "  Protocol: ${PROTOCOL}"
echo "  ${SEND_CMD}"
echo "[2/2] sender-host: ssh ${SENDER_HOST_SSH} '${SEND_CMD}'" >> "${CMDLOG}"
ssh "${SENDER_HOST_SSH}" "${SEND_CMD}" > "${MEASUREMENT_DIR}/sender-host.log" 2>&1 &
SSH_PIDS+=($!)

echo ""
echo "Both tools started. Measuring for ${DURATION}s..."
sleep "${DURATION}"

echo ""
echo "Stopping tools (SIGINT on remote hosts)..."
# Use TOOL_NAME for pkill pattern
PKILL_PATTERN="${TOOL_NAME}"
ssh "${SENDER_HOST_SSH}" "sudo pkill -INT -f ${PKILL_PATTERN}" 2>/dev/null || true
ssh "${RECEIVER_HOST_SSH}" "sudo pkill -INT -f ${PKILL_PATTERN}" 2>/dev/null || true

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

echo ""
echo "Measurement complete."
