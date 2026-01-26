#!/bin/bash
# Resolve kernel stack trace symbol+offset to source code line
#
# Usage:
#   ./resolve_stack.sh "symbol+offset" "[module]"
#   ./resolve_stack.sh "icmp_rcv+0x177" "kernel"
#   ./resolve_stack.sh "ovs_execute_actions+0x48" "openvswitch"
#
# Methods:
#   - GDB (default): Works with symbol+offset directly for most symbols
#   - For mangled symbols (.isra.N, .constprop.N): Calculates hex address
#
# Output:
#   file:line  (e.g., net/ipv4/icmp.c:1150)
#
# Environment:
#   METHOD=gdb|addr2line (default: gdb)
#   KVER=kernel_version (default: $(uname -r))
#   DEBUG_PATH=/path/to/debug (default: /usr/lib/debug/lib/modules/$KVER)

set -e

SYMBOL_OFFSET="$1"
MODULE="${2:-kernel}"
METHOD="${METHOD:-gdb}"
KVER="${KVER:-$(uname -r)}"
DEBUG_PATH="${DEBUG_PATH:-/usr/lib/debug/lib/modules/$KVER}"

# Parse symbol and offset
# Handle formats: symbol+0xoffset, symbol+offset
if [[ "$SYMBOL_OFFSET" =~ ^([^+]+)\+0?x?([0-9a-fA-F]+)$ ]]; then
    SYMBOL="${BASH_REMATCH[1]}"
    OFFSET="0x${BASH_REMATCH[2]}"
else
    echo "ERROR: Invalid format. Expected 'symbol+0xoffset'" >&2
    exit 1
fi

# Determine debug file path
get_debug_file() {
    local module="$1"

    if [[ "$module" == "kernel" ]]; then
        echo "$DEBUG_PATH/vmlinux"
    else
        # Try common module paths
        local paths=(
            "$DEBUG_PATH/kernel/net/$module/$module.ko.debug"
            "$DEBUG_PATH/kernel/net/$module.ko.debug"
            "$DEBUG_PATH/kernel/drivers/net/$module/$module.ko.debug"
            "$DEBUG_PATH/extra/$module.ko.debug"
        )

        for path in "${paths[@]}"; do
            if [[ -f "$path" ]]; then
                echo "$path"
                return 0
            fi
        done

        # Search for it
        local found
        found=$(find "$DEBUG_PATH" -name "${module}.ko.debug" 2>/dev/null | head -1)
        if [[ -n "$found" ]]; then
            echo "$found"
            return 0
        fi

        echo "ERROR: Could not find debug file for module: $module" >&2
        return 1
    fi
}

# Check if symbol is mangled (has .isra.N, .constprop.N, .cold.N suffix)
is_mangled_symbol() {
    [[ "$1" =~ \.(isra|constprop|cold|part)\.[0-9]+ ]]
}

# Get base address of symbol from debug file using nm
get_symbol_base_address() {
    local debug_file="$1"
    local symbol="$2"

    # Try exact match first, then pattern match for mangled symbols
    local addr
    addr=$(nm "$debug_file" 2>/dev/null | grep -E "^[0-9a-f]+ [tT] ${symbol}$" | awk '{print $1}' | head -1)

    if [[ -z "$addr" ]]; then
        # Try with word boundary for mangled symbols
        addr=$(nm "$debug_file" 2>/dev/null | grep " ${symbol}\$" | awk '{print $1}' | head -1)
    fi

    echo "$addr"
}

# Resolve using GDB
resolve_with_gdb() {
    local debug_file="$1"
    local symbol="$2"
    local offset="$3"

    if is_mangled_symbol "$symbol"; then
        # For mangled symbols, calculate hex address
        local base_addr
        base_addr=$(get_symbol_base_address "$debug_file" "$symbol")

        if [[ -z "$base_addr" ]]; then
            echo "ERROR: Could not find base address for symbol: $symbol" >&2
            return 1
        fi

        # Calculate target address
        local target_addr
        target_addr=$(printf '0x%x' $((0x$base_addr + $offset)))

        echo "# Mangled symbol: $symbol+$offset -> $target_addr" >&2

        # Resolve with hex address
        echo "l *$target_addr" | gdb -q "$debug_file" 2>&1 | \
            grep -E '^0x[0-9a-f]+.*is in|^[0-9]+\s+' | head -10
    else
        # Direct resolution for standard symbols
        echo "l *($symbol+$offset)" | gdb -q "$debug_file" 2>&1 | \
            grep -E '^0x[0-9a-f]+.*is in|^[0-9]+\s+' | head -10
    fi
}

# Resolve using addr2line (requires hex address)
resolve_with_addr2line() {
    local debug_file="$1"
    local symbol="$2"
    local offset="$3"

    # Get base address
    local base_addr
    base_addr=$(get_symbol_base_address "$debug_file" "$symbol")

    if [[ -z "$base_addr" ]]; then
        echo "ERROR: Could not find base address for symbol: $symbol" >&2
        return 1
    fi

    # Calculate target address
    local target_addr
    target_addr=$(printf '0x%x' $((0x$base_addr + $offset)))

    addr2line -e "$debug_file" -f -p "$target_addr" 2>&1
}

# Extract just file:line from GDB output
extract_file_line() {
    # Parse "0xffffffff817c1150 is in icmp_rcv (net/ipv4/icmp.c:1150)."
    grep -oP '\([^)]+:[0-9]+\)' | tr -d '()' | head -1
}

# Main
DEBUG_FILE=$(get_debug_file "$MODULE") || exit 1

if [[ ! -f "$DEBUG_FILE" ]]; then
    echo "ERROR: Debug file not found: $DEBUG_FILE" >&2
    exit 1
fi

echo "# Resolving: $SYMBOL+$OFFSET [$MODULE]" >&2
echo "# Debug file: $DEBUG_FILE" >&2
echo "# Method: $METHOD" >&2

case "$METHOD" in
    gdb)
        OUTPUT=$(resolve_with_gdb "$DEBUG_FILE" "$SYMBOL" "$OFFSET")
        echo "$OUTPUT"

        # Extract and print just file:line
        FILE_LINE=$(echo "$OUTPUT" | extract_file_line)
        if [[ -n "$FILE_LINE" ]]; then
            echo "---"
            echo "RESULT: $FILE_LINE"
        fi
        ;;
    addr2line)
        resolve_with_addr2line "$DEBUG_FILE" "$SYMBOL" "$OFFSET"
        ;;
    *)
        echo "ERROR: Unknown method: $METHOD" >&2
        exit 1
        ;;
esac
