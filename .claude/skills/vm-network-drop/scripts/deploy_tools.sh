#!/bin/bash
# Deploy icmp_path_tracer.py to sender and receiver hosts for VM drop detection.
set -e

for VAR in SENDER_HOST_SSH RECEIVER_HOST_SSH LOCAL_TOOLS; do
    if [ -z "${!VAR}" ]; then
        echo "Error: ${VAR} is not set" >&2
        exit 1
    fi
done

TOOL="${LOCAL_TOOLS}/linux-network-stack/packet-drop/icmp_path_tracer.py"
if [ ! -f "${TOOL}" ]; then
    echo "Error: Tool not found: ${TOOL}" >&2
    exit 1
fi

echo "Deploying icmp_path_tracer.py for VM drop detection..."

echo "[1/2] Sender Host (${SENDER_HOST_SSH})..."
scp -q "${TOOL}" "${SENDER_HOST_SSH}:/tmp/"
echo "  - icmp_path_tracer.py -> /tmp/"

echo "[2/2] Receiver Host (${RECEIVER_HOST_SSH})..."
scp -q "${TOOL}" "${RECEIVER_HOST_SSH}:/tmp/"
echo "  - icmp_path_tracer.py -> /tmp/"

echo "Tool deployment complete."
