---
name: network-env-collector
description: Collect network environment information from KVM virtualization hosts. This skill should be used when users need to gather system network info (OVS internal ports, bridges, physical NICs, bonds) or VM network info (virtio NIC to vnet mapping, qemu-kvm PID, vhost process PIDs, OVS bridge topology). Triggers on requests like "get network info", "show OVS configuration", "find VM vnet mapping", "get qemu process", "find vhost threads", or "collect network environment".
---

# Network Environment Collector

## Overview

This skill provides tools for collecting network environment information from KVM virtualization hosts running OVS (Open vSwitch). It handles two main scenarios:

1. **System Network**: OVS internal ports (port-xxx), their IP addresses, bridges, and physical NICs (including OVS/Linux bonds)
2. **VM Network**: virtio NIC to host vnet mapping, qemu-kvm process PID, vhost thread PIDs, OVS bridge topology for VM traffic

## Quick Start

### System Network Information

To collect all system network information from a host:

```bash
python3 scripts/network_env_collector.py system \
  --host <HOST_IP> \
  --user <USERNAME> \
  [--password <PASSWORD>] \
  [--type <NETWORK_TYPE>]
```

**Parameters:**
- `--host`: Target host IP address
- `--user`: SSH username
- `--password`: (Optional) SSH password for authentication
- `--type`: (Optional) Filter by network type (mgt, storage, access, vpc, internal)
- `--timeout`: (Optional) SSH command timeout in seconds (default: 60)

**Example:**
```bash
python3 scripts/network_env_collector.py system --host 192.168.75.101 --user smartx
```

### VM Network Information

To collect VM network information for all NICs (by VM UUID):

```bash
python3 scripts/network_env_collector.py vm \
  --uuid <VM_UUID> \
  --host-ip <HOST_IP> \
  --host-user <HOST_USERNAME> \
  [--host-password <HOST_PASSWORD>] \
  [--vm-host <VM_IP>] \
  [--vm-user <VM_USERNAME>] \
  [--vm-password <VM_PASSWORD>]
```

**Parameters:**
- `--uuid`: VM UUID (domain name) - **required**
- `--host-ip`: Hypervisor host IP address - **required**
- `--host-user`: Host SSH username - **required**
- `--host-password`: (Optional) Host SSH password
- `--vm-host`: (Optional) VM IP address for getting NIC names/IPs inside VM
- `--vm-user`: (Optional) VM SSH username
- `--vm-password`: (Optional) VM SSH password
- `--timeout`: (Optional) SSH command timeout in seconds (default: 60)

**Example:**
```bash
# Collect all NICs info (host only, no VM internal info)
python3 scripts/network_env_collector.py vm \
  --uuid ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --host-ip 192.168.75.101 --host-user smartx

# Collect with VM internal NIC names and IPs
python3 scripts/network_env_collector.py vm \
  --uuid ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --host-ip 192.168.75.101 --host-user smartx \
  --vm-host 192.168.73.72 --vm-user smartx
```

## Output Format

### System Network Output

```json
[
  {
    "port_name": "port-storage",
    "port_type": "storage",
    "ip_address": "10.37.166.11",
    "ovs_bridge": "ovsbr-3wy00kr85",
    "uplink_bridge": "ovsbr-3wy00kr85",
    "physical_nics": [
      {
        "name": "bond-m-3wy00kr85",
        "speed": "10000Mb/s",
        "is_bond": true,
        "bond_type": "ovs",
        "bond_members": ["eth1", "eth2"],
        "member_speeds": {"eth1": "10000Mb/s", "eth2": "10000Mb/s"}
      }
    ]
  }
]
```

### VM Network Output

```json
{
  "vm_uuid": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
  "vm_name": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
  "qemu_pid": 18627,
  "nics": [
    {
      "mac": "52:54:00:51:a3:8b",
      "vm_nic_name": "ens4",
      "vm_ip": "192.168.73.72",
      "host_vnet": "vnet0",
      "tap_fds": [47, 48, 49, 50],
      "vhost_fds": [51, 52, 53, 54],
      "vhost_pids": [
        {"pid": 18739, "name": "vhost-18627"},
        {"pid": 18740, "name": "vhost-18627"},
        {"pid": 18741, "name": "vhost-18627"},
        {"pid": 18742, "name": "vhost-18627"}
      ],
      "ovs_bridge": "ovsbr-uovhon43t",
      "uplink_bridge": "ovsbr-uovhon43t",
      "physical_nics": [
        {
          "name": "eth0",
          "speed": "10000Mb/s",
          "is_bond": false,
          "bond_type": "",
          "bond_members": [],
          "member_speeds": {}
        }
      ]
    }
  ]
}
```

## Key Features

### SSH Connection
Uses paramiko for persistent SSH connections. Supports:
- Key-based authentication (SSH agent or key files)
- Password authentication when `--password` is provided
- Auto-reconnection on connection failures

**Dependency:** Requires `paramiko` library (`pip install paramiko`)

### OVS Topology Detection
- Detects OVS internal ports matching `port-*` pattern
- Handles patch port scenarios where internal port and physical NIC are on different bridges (bridge vs bridge-uplink)
- Identifies both OVS bonds and Linux bonds

### Bond Detection
- **OVS Bond**: Detected via `ovs-appctl bond/show`
- **Linux Bond**: Detected via `/sys/class/net/<bond>/bonding/slaves`
- Reports bond members and individual member speeds

### Physical NIC Speed
Uses `ethtool` to retrieve NIC speed information. In nested virtualization environments, speed may show as "Unknown!".

### QEMU-KVM Process Detection (VM Network)
- Retrieves the qemu-kvm process PID for the VM on the host
- Uses multiple methods in order: `virsh dompid`, PID file, `ps` grep
- Most reliable method is `virsh dompid`

### Tap/Vhost FD Mapping (VM Network)
- Maps tap file descriptors to vnet interfaces via `/proc/<pid>/fdinfo`
- Maps vhost file descriptors to vnets based on fd allocation order
- Supports multi-queue virtio-net (multiple tap/vhost fds per NIC)

### Vhost Process Detection (VM Network)
- Identifies all vhost kernel threads associated with a VM's NICs
- Groups vhost PIDs by vnet interface based on PID and fd allocation order
- Vhost threads handle virtio-net packet processing (vhost-net)
- Thread naming convention: `vhost-<qemu_pid>`

## Architecture Notes

### System Network Types
- **mgt**: Management network (port-mgt)
- **storage**: Storage network (port-storage)
- **access**: Access network (port-access)
- **vpc**: VPC network (port-vpc)
- **internal**: Internal network (port-internal)

### OVS Bridge Topology
In some configurations, OVS uses patch ports to connect bridges:
- Internal port resides on `ovsbr-xxxxx`
- Physical NIC resides on `ovsbr-xxxxx-uplink`

The tool automatically detects this topology and reports the correct uplink bridge.

## Resources

### scripts/
- `network_env_collector.py`: Main collection script supporting both system and VM network info gathering
