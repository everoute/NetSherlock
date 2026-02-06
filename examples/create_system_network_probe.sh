#!/bin/bash

##############################################################################
# Create System Network Probe Task - NetSherlock
#
# This script demonstrates how to create a system network (host-to-host)
# network probe diagnosis task via the NetSherlock API.
#
# Usage: bash create_system_network_probe.sh [PROBE_TYPE]
# Examples:
#   bash create_system_network_probe.sh latency
#   bash create_system_network_probe.sh packet_drop
#   bash create_system_network_probe.sh connectivity
#
# Environment Variables:
#   API_URL: Backend API endpoint (default: http://localhost:8000)
#   API_KEY: API authentication key (default: test-key-12345)
#   SRC_HOST: Source host IP (default: 192.168.79.11)
#   DST_HOST: Destination host IP (default: 192.168.79.12)
#
##############################################################################

set -e

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-test-key-12345}"
SRC_HOST="${SRC_HOST:-192.168.79.11}"
DST_HOST="${DST_HOST:-192.168.79.12}"

# Probe type: latency, packet_drop, or connectivity
PROBE_TYPE="${1:-latency}"

# Validate probe type
if [[ ! "$PROBE_TYPE" =~ ^(latency|packet_drop|connectivity)$ ]]; then
    echo "❌ Invalid probe type: $PROBE_TYPE"
    echo "Valid types: latency, packet_drop, connectivity"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  Creating System Network Probe Diagnosis Task            ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}📋 Task Configuration:${NC}"
echo "  • Network Type: system (host-to-host)"
echo "  • Diagnosis Type: $PROBE_TYPE"
echo "  • Source Host: $SRC_HOST"
echo "  • Destination Host: $DST_HOST"
echo "  • API URL: $API_URL"
echo ""

# Prepare request body
read -r -d '' REQUEST_BODY << 'EOF' || true
{
  "network_type": "system",
  "diagnosis_type": "$PROBE_TYPE",
  "src_host": "$SRC_HOST",
  "dst_host": "$DST_HOST",
  "description": "System network $PROBE_TYPE probe from $SRC_HOST to $DST_HOST"
}
EOF

# Substitute variables in request body
REQUEST_BODY=$(echo "$REQUEST_BODY" | sed "s/\$PROBE_TYPE/$PROBE_TYPE/g" | sed "s/\$SRC_HOST/$SRC_HOST/g" | sed "s/\$DST_HOST/$DST_HOST/g")

echo -e "${YELLOW}📨 Sending Request:${NC}"
echo "  POST $API_URL/diagnose"
echo "  Headers:"
echo "    - X-API-Key: $API_KEY"
echo "    - Content-Type: application/json"
echo ""
echo "  Body:"
echo "$REQUEST_BODY" | jq '.' 2>/dev/null || echo "$REQUEST_BODY"
echo ""

# Send request
echo -e "${YELLOW}⏳ Waiting for response...${NC}"
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/diagnose" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_BODY")

# Check if request was successful
if echo "$RESPONSE" | jq . >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Success!${NC}"
    echo ""
    echo -e "${YELLOW}📊 Response:${NC}"
    echo "$RESPONSE" | jq '.'
    echo ""
    
    # Extract diagnosis ID
    DIAGNOSIS_ID=$(echo "$RESPONSE" | jq -r '.diagnosis_id // empty')
    
    if [ -n "$DIAGNOSIS_ID" ]; then
        echo -e "${GREEN}✓ Diagnosis ID: $DIAGNOSIS_ID${NC}"
        echo ""
        echo -e "${BLUE}🔍 Next Steps:${NC}"
        echo ""
        echo "1️⃣  Check task status:"
        echo "   curl -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnose/$DIAGNOSIS_ID\""
        echo ""
        echo "2️⃣  List all tasks:"
        echo "   curl -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnoses?limit=10\""
        echo ""
        echo "3️⃣  Get diagnosis report (after completion):"
        echo "   curl -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnose/$DIAGNOSIS_ID/report\""
        echo ""
        echo "4️⃣  Cancel the task (if still pending/waiting):"
        echo "   curl -X POST -H \"X-API-Key: $API_KEY\" \"$API_URL/diagnose/$DIAGNOSIS_ID/cancel\""
        echo ""
    fi
else
    echo -e "${RED}❌ Error!${NC}"
    echo ""
    echo -e "${YELLOW}Response:${NC}"
    echo "$RESPONSE"
    exit 1
fi

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  Task creation complete!                                 ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
