#!/bin/bash
# Start system_*_path_tracer on both hosts (v2).
#
# Supports multi-protocol (ICMP MVP, TCP/UDP reserved) with configurable:
#   - DIRECTION: rx (default) or tx for ICMP
#   - OUTPUT_MODE: verbose (default) or stats
#   - PORT: port filter for TCP/UDP
#
# Receiver Host (primary): traces A→B traffic (--src-ip=A, --dst-ip=B)
# Sender Host (secondary): traces B→A traffic (--src-ip=B, --dst-ip=A)
#
# Receiver starts first to avoid missing early packets.

set -e

# v2: Protocol and mode parameters (from measure.py env)
PROTOCOL=${PROTOCOL:-icmp}
DIRECTION=${DIRECTION:-rx}
FOCUS=${FOCUS:-drop}
OUTPUT_MODE=${OUTPUT_MODE:-verbose}
TOOL_NAME=${TOOL_NAME:-system_icmp_path_tracer.py}

RECEIVER_WARMUP=${RECEIVER_WARMUP:-2}
SHUTDOWN_WAIT=${SHUTDOWN_WAIT:-3}
TIMEOUT_MS=${TIMEOUT_MS:-1000}

# v2: Optional TCP/UDP parameters
PORT=${PORT:-}
STATS_INTERVAL=${STATS_INTERVAL:-5}

for VAR in SENDER_HOST_SSH SENDER_IP SENDER_PHY_IF RECEIVER_HOST_SSH RECEIVER_IP RECEIVER_PHY_IF DURATION MEASUREMENT_DIR; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

mkdir -p "${MEASUREMENT_DIR}"
CMDLOG="${MEASUREMENT_DIR}/commands.log"

# Build tool-specific arguments
build_tool_args() {
    local src_ip=$1
    local dst_ip=$2
    local phy_if=$3
    local args=""

    case ${PROTOCOL} in
        icmp)
            # ICMP: direction and verbose
            args="--src-ip ${src_ip} --dst-ip ${dst_ip} --phy-iface ${phy_if} --timeout-ms ${TIMEOUT_MS}"
            args="${args} --direction ${DIRECTION}"
            if [ "${OUTPUT_MODE}" = "verbose" ]; then
                args="${args} --verbose"
            fi
            ;;
        tcp|udp)
            # TCP/UDP: port, verbose or stats (reserved for future)
            args="--src-ip ${src_ip} --dst-ip ${dst_ip} --phy-iface ${phy_if} --timeout-ms ${TIMEOUT_MS}"
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

echo "=== System Network Path Tracer Measurement (v2) ===" >> "${CMDLOG}"
echo "Timestamp: $(date)" >> "${CMDLOG}"
echo "Sender: ${SENDER_HOST_SSH} (${SENDER_IP}) IF=${SENDER_PHY_IF}" >> "${CMDLOG}"
echo "Receiver: ${RECEIVER_HOST_SSH} (${RECEIVER_IP}) IF=${RECEIVER_PHY_IF}" >> "${CMDLOG}"
echo "Protocol=${PROTOCOL}, Direction=${DIRECTION}, Focus=${FOCUS}, OutputMode=${OUTPUT_MODE}" >> "${CMDLOG}"
echo "DURATION=${DURATION}s, TIMEOUT=${TIMEOUT_MS}ms" >> "${CMDLOG}"
echo "" >> "${CMDLOG}"

declare -a SSH_PIDS=()

# [1/2] Receiver Host (primary): traces traffic from Sender → Receiver
RECV_ARGS=$(build_tool_args "${SENDER_IP}" "${RECEIVER_IP}" "${RECEIVER_PHY_IF}")
RECV_CMD="sudo python3 /tmp/${TOOL_NAME} ${RECV_ARGS}"
echo "[1/2] receiver-host (primary, traces ${SENDER_IP}→${RECEIVER_IP}):"
echo "  Protocol: ${PROTOCOL}, Direction: ${DIRECTION}"
echo "  ${RECV_CMD}"
echo "[1/2] receiver-host: ssh ${RECEIVER_HOST_SSH} '${RECV_CMD}'" >> "${CMDLOG}"
ssh "${RECEIVER_HOST_SSH}" "${RECV_CMD}" > "${MEASUREMENT_DIR}/receiver-host.log" 2>&1 &
SSH_PIDS+=($!)

sleep "${RECEIVER_WARMUP}"

# [2/2] Sender Host (secondary): traces traffic from Receiver → Sender
SEND_ARGS=$(build_tool_args "${RECEIVER_IP}" "${SENDER_IP}" "${SENDER_PHY_IF}")
SEND_CMD="sudo python3 /tmp/${TOOL_NAME} ${SEND_ARGS}"
echo "[2/2] sender-host (secondary, traces ${RECEIVER_IP}→${SENDER_IP}):"
echo "  Protocol: ${PROTOCOL}, Direction: ${DIRECTION}"
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
ssh "${RECEIVER_HOST_SSH}" "sudo pkill -INT -f ${PKILL_PATTERN}" 2>/dev/null || true
ssh "${SENDER_HOST_SSH}" "sudo pkill -INT -f ${PKILL_PATTERN}" 2>/dev/null || true

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
