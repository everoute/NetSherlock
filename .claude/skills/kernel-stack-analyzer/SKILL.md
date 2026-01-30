---
name: kernel-stack-analyzer
description: |
  Analyze kernel call stacks from kfree_skb tracing tools to distinguish between
  true packet drops and normal packet processing completions.

  Resolves stack trace addresses to source code lines using GDB or addr2line,
  then analyzes the calling context to classify each stack trace.

  Trigger keywords: analyze kernel stack, resolve stack trace, kernel drop analysis,
  kfree_skb analysis, packet drop stack, 内核调用栈分析, 丢包分析

allowed-tools: Read, Write, Bash, Grep, Glob
---

# Kernel Stack Analyzer Skill

## Overview

This skill analyzes kernel call stacks from the `kernel_drop_stack_stats_summary_all.py` BPF tool output. It distinguishes between:

- **TRUE_DROP**: Actual packet drops (errors, policy, resource limits)
- **NORMAL_PROCESSING**: Normal packet handling where `kfree_skb` is called as part of normal processing completion (e.g., packet delivered to socket, clones/copies freed, helper buffers cleaned up)

## Usage

### Input Types

1. **Tool output file**: Path to saved output from `kernel_drop_stack_stats_summary_all.py`
2. **Pasted output**: Direct paste of tool output in the conversation
3. **Single stack trace**: Individual `symbol+offset [module]` entries

### Workflow

```
Step 1: Parse stack traces from input
Step 2: Resolve addresses to source lines (SSH to target host)
Step 3: Analyze source context (local kernel source)
Step 4: Classify and report
```

## Scripts

### parse_stack_output.py

Parses tool output into structured JSON:

```bash
python3 .claude/skills/kernel-stack-analyzer/scripts/parse_stack_output.py < output.log
```

Output:
```json
{
  "entries": [
    {
      "rank": 1,
      "count": 81,
      "device": "port-mgt",
      "stack_id": 617,
      "flow": "192.168.70.31 -> 192.168.70.32 (ICMP)",
      "frames": [
        {"symbol": "kfree_skb", "offset": "0x1", "module": "kernel"},
        {"symbol": "icmp_rcv", "offset": "0x177", "module": "kernel"},
        ...
      ]
    }
  ]
}
```

### resolve_stack.sh

Resolves stack addresses to source lines on the target host:

```bash
# Single symbol resolution
ssh TARGET_HOST "bash -s" < scripts/resolve_stack.sh "icmp_rcv+0x177" "kernel"

# Output: net/ipv4/icmp.c:1150
```

Handles:
- Standard kernel symbols: Direct GDB resolution
- Mangled symbols (`.isra.N`): Hex address calculation
- Module symbols: Uses module debug file

## Configuration

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `target_host` | SSH target for resolution | `smartx@192.168.70.31` |
| `kernel_source` | Local kernel source path | `../kernel` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `method` | `gdb` | Resolution method: `gdb` or `addr2line` |

## Example Session

```
User: Analyze this kernel drop output:
[paste tool output]

Skill response:
Parsed 5 unique stack traces from input.

Resolving addresses on smartx@192.168.70.31...

=== Classification Results ===

Stack #617 (81 calls): TRUE_DROP
  Flow: 192.168.70.31 -> 192.168.70.32 (ICMP)
  Location: net/ipv4/icmp.c:1150
  Context: drop: label, returns NET_RX_DROP
  Reason: ICMP handler returned failure

Stack #305 (42 calls): NORMAL_PROCESSING
  Flow: 10.0.0.1 -> 10.0.0.2 (UDP:53)
  Location: net/openvswitch/datapath.c:539
  Context: out: cleanup label
  Reason: OVS upcall buffer cleanup (user_skb/nskb, not original packet)

Summary: 81 TRUE_DROP, 42 NORMAL_PROCESSING
```

## Drop Context Indicators

### True Drop Indicators

| Indicator | Examples |
|-----------|----------|
| Labels | `drop:`, `discard_it:`, `error:`, `csum_error:`, `bad:` |
| Returns | `NET_RX_DROP`, `-EINVAL`, `-ENOMEM`, `-ENOBUFS` |
| Stats | `*_MIB_INERRORS`, `*_MIB_CSUMERRORS`, `*_MIB_INDISCARDS` |

### Normal Processing Indicators

| Indicator | Examples |
|-----------|----------|
| Labels | `out:`, `done:`, `success:`, `free:` |
| Returns | `NET_RX_SUCCESS`, `0` |
| Context | Processing completed normally: packet consumed/delivered, `skb_clone()`/`skb_copy()` freed, helper buffers cleaned up |

## Prerequisites

1. **SSH access** to target host with sudo
2. **Debuginfo packages** installed on target:
   - `kernel-debuginfo` (provides vmlinux)
   - `openvswitch-debuginfo` (for OVS module symbols)
3. **Local kernel source** at `../kernel` (same version family as target)

## Related Skills

- [network-env-collector](../network-env-collector/SKILL.md) - Collect network environment info
- [vm-latency-analysis](../vm-latency-analysis/SKILL.md) - Latency breakdown analysis

## Debuginfo Paths

```
/usr/lib/debug/lib/modules/$(uname -r)/vmlinux                          # kernel
/usr/lib/debug/lib/modules/$(uname -r)/kernel/net/openvswitch/openvswitch.ko.debug  # OVS
```
