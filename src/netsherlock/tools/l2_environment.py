"""L2 Layer Tools: Environment Awareness.

MCP tools for collecting network environment and topology information.
These tools gather the context needed for targeted measurements.

The core collection logic is adapted from:
troubleshooting-tools/test/tools/network_env_collector.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import structlog

from netsherlock.config.settings import get_settings
from netsherlock.core.ssh_manager import SSHManager
from netsherlock.schemas.environment import (
    NetworkEndpoint,
    NetworkPath,
    NetworkType,
    PathSegment,
    PhysicalNIC,
    SystemNetworkEnv,
    SystemNetworkInfo,
    VhostInfo,
    VMNetworkEnv,
    VMNicInfo,
)

logger = structlog.get_logger(__name__)


@dataclass
class EnvCollectionResult:
    """Result of environment collection."""

    success: bool
    host: str
    data: VMNetworkEnv | SystemNetworkEnv | None = None
    error: str | None = None


class NetworkEnvCollector:
    """Network environment information collector.

    Adapted from troubleshooting-tools/test/tools/network_env_collector.py
    with integration into our SSH manager and Pydantic models.
    """

    def __init__(self, ssh: SSHManager, host: str):
        """Initialize collector.

        Args:
            ssh: SSH manager instance
            host: Target host IP address
        """
        self.ssh = ssh
        self.host = host
        self._bridge_nics_cache: dict[str, list[PhysicalNIC]] = {}

    def _execute(self, cmd: str, sudo: bool = False) -> tuple[str, str, int]:
        """Execute command on remote host."""
        if sudo:
            cmd = f"sudo {cmd}"
        result = self.ssh.execute(self.host, cmd)
        return result.stdout, result.stderr, result.exit_code

    def get_ovs_internal_ports(self) -> list[tuple[str, str]]:
        """Get all OVS internal ports (port-xxx pattern).

        Returns:
            List of (port_name, bridge_name) tuples
        """
        stdout, _, _ = self._execute("ovs-vsctl show", sudo=True)

        ports = []
        current_bridge = None

        for line in stdout.split("\n"):
            line = line.strip()
            if line.startswith("Bridge "):
                match = re.match(r'Bridge\s+"?([^"\s]+)"?', line)
                if match:
                    current_bridge = match.group(1)
            elif line.startswith("Port ") and current_bridge:
                match = re.match(r'Port\s+"?(port-[^"\s]+)"?', line)
                if match:
                    port_name = match.group(1)
                    ports.append((port_name, current_bridge))

        return ports

    def get_port_ip(self, port_name: str) -> str:
        """Get IP address of an interface."""
        cmd = f"/sbin/ip addr show {port_name} 2>/dev/null || ip addr show {port_name}"
        stdout, _, ret = self._execute(cmd)
        if ret != 0:
            return ""

        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", stdout)
        return match.group(1) if match else ""

    def get_bridge_ports(self, bridge: str) -> list[str]:
        """Get all ports on an OVS bridge."""
        stdout, _, _ = self._execute(f"ovs-vsctl list-ports {bridge}", sudo=True)
        return [p.strip() for p in stdout.strip().split("\n") if p.strip()]

    def get_patch_peer_bridge(self, bridge: str) -> str | None:
        """Find peer bridge connected via patch ports."""
        uplink_bridge = f"{bridge}-uplink"
        _, _, ret = self._execute(f"ovs-vsctl br-exists {uplink_bridge}", sudo=True)
        if ret == 0:
            return uplink_bridge
        return None

    def get_physical_nics_on_bridge(self, bridge: str) -> list[PhysicalNIC]:
        """Get physical NICs on a bridge (handles bonds)."""
        if bridge in self._bridge_nics_cache:
            return self._bridge_nics_cache[bridge]

        ports = self.get_bridge_ports(bridge)
        if not ports:
            self._bridge_nics_cache[bridge] = []
            return []

        # Batch get interface types and bond modes
        ports_str = " ".join(ports)
        stdout, _, _ = self._execute(
            f"bash -c 'for p in {ports_str}; do "
            f"t=$(ovs-vsctl get interface $p type 2>/dev/null); "
            f"b=$(ovs-vsctl get port $p bond_mode 2>/dev/null); "
            f'echo "PORT:$p TYPE:$t BOND:$b"; done\'',
            sudo=True,
        )

        # Parse results
        port_info = {}
        for line in stdout.strip().split("\n"):
            if not line.startswith("PORT:"):
                continue
            parts = line.split()
            port_name = parts[0].replace("PORT:", "")
            port_type = ""
            is_bond = False
            for part in parts[1:]:
                if part.startswith("TYPE:"):
                    port_type = part.replace("TYPE:", "").strip('"')
                elif part.startswith("BOND:"):
                    bond_val = part.replace("BOND:", "").strip('"[]')
                    is_bond = bool(bond_val)
            port_info[port_name] = {"type": port_type, "is_bond": is_bond}

        # Identify physical ports
        physical_port_names = []
        for port, info in port_info.items():
            if info["is_bond"] or (info["type"] in ["", "system"] and not port.startswith("vnet")):
                physical_port_names.append(port)

        if not physical_port_names:
            self._bridge_nics_cache[bridge] = []
            return []

        # Get NIC info
        physical_nics = []
        for port in physical_port_names:
            # Check for bond
            if port_info[port]["is_bond"]:
                nic = self._get_bond_nic_info(port, "ovs")
                if nic:
                    physical_nics.append(nic)
                    continue

            # Check Linux bond
            nic = self._get_bond_nic_info(port, "linux")
            if nic:
                physical_nics.append(nic)
                continue

            # Single physical NIC
            speed = self._get_nic_speed(port)
            physical_nics.append(
                PhysicalNIC(name=port, speed=speed, is_bond=False)
            )

        self._bridge_nics_cache[bridge] = physical_nics
        return physical_nics

    def _get_bond_nic_info(self, port: str, bond_type: Literal["ovs", "linux"]) -> PhysicalNIC | None:
        """Get bond NIC information."""
        if bond_type == "ovs":
            stdout, _, ret = self._execute(f"ovs-appctl bond/show {port}", sudo=True)
            if ret != 0:
                return None

            members = []
            for line in stdout.split("\n"):
                line = line.strip()
                if line.startswith("member ") or line.startswith("slave "):
                    match = re.match(r"(?:member|slave)\s+(\S+):", line)
                    if match:
                        members.append(match.group(1))

            if not members:
                return None

        else:  # linux bond
            stdout, _, ret = self._execute(
                f"cat /sys/class/net/{port}/bonding/slaves 2>/dev/null"
            )
            if ret != 0:
                return None
            members = stdout.strip().split()
            if not members:
                return None

        # Get member speeds
        member_speeds = {}
        for member in members:
            member_speeds[member] = self._get_nic_speed(member)

        return PhysicalNIC(
            name=port,
            speed=member_speeds.get(members[0], "unknown") if members else "unknown",
            is_bond=True,
            bond_type=bond_type,
            bond_members=members,
            member_speeds=member_speeds,
        )

    def _get_nic_speed(self, nic: str) -> str:
        """Get NIC speed using ethtool."""
        stdout, _, ret = self._execute(f"ethtool {nic} 2>/dev/null | grep Speed", sudo=True)
        if ret != 0 or not stdout.strip():
            return "unknown"

        match = re.search(r"Speed:\s*(\S+)", stdout)
        return match.group(1) if match else "unknown"

    def collect_system_network(self, port_type: str | None = None) -> list[SystemNetworkInfo]:
        """Collect system network information."""
        results = []
        internal_ports = self.get_ovs_internal_ports()

        for port_name, bridge in internal_ports:
            match = re.match(r"port-(\w+)", port_name)
            if not match:
                continue

            p_type = match.group(1)
            if port_type and p_type != port_type:
                continue

            ip_address = self.get_port_ip(port_name)
            uplink_bridge = self.get_patch_peer_bridge(bridge)

            if uplink_bridge:
                physical_nics = self.get_physical_nics_on_bridge(uplink_bridge)
            else:
                uplink_bridge = bridge
                physical_nics = self.get_physical_nics_on_bridge(bridge)

            results.append(
                SystemNetworkInfo(
                    port_name=port_name,
                    port_type=p_type,
                    ip_address=ip_address,
                    ovs_bridge=bridge,
                    uplink_bridge=uplink_bridge,
                    physical_nics=physical_nics,
                )
            )

        return results

    def get_qemu_pid_by_vm(self, vm_name: str) -> int:
        """Get qemu-kvm process PID by VM name."""
        # Try virsh dompid first
        stdout, _, ret = self._execute(f"virsh dompid {vm_name}", sudo=True)
        if ret == 0 and stdout.strip():
            try:
                return int(stdout.strip())
            except ValueError:
                pass

        # Fallback to ps
        stdout, _, ret = self._execute(
            f"ps aux | grep '[q]emu.*guest={vm_name}' | awk '{{print $2}}' | head -1"
        )
        if ret == 0 and stdout.strip():
            try:
                return int(stdout.strip())
            except ValueError:
                pass

        return 0

    def get_vm_nics_from_xml(self, vm_name: str) -> list[dict]:
        """Get all VM NICs info from virsh dumpxml."""
        stdout, _, ret = self._execute(f"virsh dumpxml {vm_name}", sudo=True)
        if ret != 0:
            return []

        nics = []
        interfaces = re.findall(
            r"<interface[^>]*type='bridge'[^>]*>.*?</interface>",
            stdout,
            re.DOTALL,
        )

        for iface in interfaces:
            nic_info = {}
            mac_match = re.search(r"<mac\s+address='([^']+)'", iface)
            if mac_match:
                nic_info["mac"] = mac_match.group(1)

            vnet_match = re.search(r"<target\s+dev='([^']+)'", iface)
            if vnet_match:
                nic_info["vnet"] = vnet_match.group(1)

            queues_match = re.search(r"queues='(\d+)'", iface)
            nic_info["queues"] = int(queues_match.group(1)) if queues_match else 1

            if "mac" in nic_info and "vnet" in nic_info:
                nics.append(nic_info)

        return nics

    def get_tap_fd_mapping(self, qemu_pid: int) -> dict[str, list[int]]:
        """Get mapping of vnet to tap fds."""
        if qemu_pid <= 0:
            return {}

        stdout, _, ret = self._execute(
            f"ls -la /proc/{qemu_pid}/fd 2>/dev/null | grep '/dev/net/tun'", sudo=True
        )
        if ret != 0 or not stdout.strip():
            return {}

        tap_fds = []
        for line in stdout.strip().split("\n"):
            match = re.search(r"\s(\d+)\s+->", line)
            if match:
                tap_fds.append(int(match.group(1)))

        if not tap_fds:
            return {}

        # Read fdinfo to get vnet names
        fd_list = " ".join(str(fd) for fd in tap_fds)
        stdout, _, ret = self._execute(
            f"bash -c 'for fd in {fd_list}; do echo FD:$fd; "
            f'grep "^iff:" /proc/{qemu_pid}/fdinfo/$fd 2>/dev/null; done\'',
            sudo=True,
        )

        vnet_to_fds: dict[str, list[int]] = {}
        current_fd = None
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("FD:"):
                current_fd = int(line[3:])
            elif line.startswith("iff:") and current_fd is not None:
                vnet = line.split()[-1]
                if vnet not in vnet_to_fds:
                    vnet_to_fds[vnet] = []
                vnet_to_fds[vnet].append(current_fd)

        for vnet in vnet_to_fds:
            vnet_to_fds[vnet].sort()

        return vnet_to_fds

    def get_vhost_pids_by_qemu(self, qemu_pid: int) -> list[VhostInfo]:
        """Get vhost process PIDs for a qemu process."""
        if qemu_pid <= 0:
            return []

        stdout, _, ret = self._execute(f"ps -eo pid,comm | grep 'vhost-{qemu_pid}'")
        if ret != 0 or not stdout.strip():
            return []

        vhost_list = []
        for line in stdout.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    pid = int(parts[0])
                    name = parts[1]
                    vhost_list.append(VhostInfo(pid=pid, name=name))
                except ValueError:
                    continue

        return vhost_list

    def get_vnet_bridge(self, vnet: str) -> str:
        """Get OVS bridge for a vnet interface."""
        stdout, _, ret = self._execute(f"ovs-vsctl port-to-br {vnet}", sudo=True)
        if ret != 0:
            return ""
        return stdout.strip()

    def collect_vm_network(self, vm_uuid: str) -> VMNetworkEnv | None:
        """Collect VM network environment information."""
        vm_name = vm_uuid

        qemu_pid = self.get_qemu_pid_by_vm(vm_name)
        if qemu_pid <= 0:
            logger.warning("qemu_pid_not_found", vm=vm_uuid)
            return None

        nics_from_xml = self.get_vm_nics_from_xml(vm_name)
        if not nics_from_xml:
            logger.warning("no_nics_found", vm=vm_uuid)
            return None

        tap_fd_mapping = self.get_tap_fd_mapping(qemu_pid)
        vhost_pids = self.get_vhost_pids_by_qemu(qemu_pid)

        # Group vhost pids by vnet based on ordering
        vnets_sorted = sorted(
            tap_fd_mapping.items(),
            key=lambda x: min(x[1]) if x[1] else float("inf"),
        )
        vhost_pids.sort(key=lambda x: x.pid)

        vnet_to_vhost: dict[str, list[VhostInfo]] = {}
        thread_index = 0
        for vnet, tap_fds in vnets_sorted:
            queue_count = len(tap_fds)
            if thread_index + queue_count <= len(vhost_pids):
                vnet_to_vhost[vnet] = vhost_pids[thread_index : thread_index + queue_count]
                thread_index += queue_count

        # Build NIC info
        nics = []
        for nic_xml in nics_from_xml:
            mac = nic_xml["mac"]
            vnet = nic_xml["vnet"]

            bridge = self.get_vnet_bridge(vnet)
            uplink_bridge = self.get_patch_peer_bridge(bridge) if bridge else None

            if uplink_bridge:
                physical_nics = self.get_physical_nics_on_bridge(uplink_bridge)
            elif bridge:
                uplink_bridge = bridge
                physical_nics = self.get_physical_nics_on_bridge(bridge)
            else:
                physical_nics = []

            nics.append(
                VMNicInfo(
                    mac=mac,
                    host_vnet=vnet,
                    tap_fds=tap_fd_mapping.get(vnet, []),
                    vhost_pids=vnet_to_vhost.get(vnet, []),
                    ovs_bridge=bridge,
                    uplink_bridge=uplink_bridge or "",
                    physical_nics=physical_nics,
                )
            )

        return VMNetworkEnv(
            vm_uuid=vm_uuid,
            vm_name=vm_name,
            host=self.host,
            qemu_pid=qemu_pid,
            nics=nics,
        )


def collect_vm_network_env(
    vm_id: str,
    host: str,
) -> EnvCollectionResult:
    """Collect VM network environment information.

    This is an L2 layer tool for gathering VM network topology including:
    - vnet interfaces
    - TAP/vhost file descriptors
    - vhost process PIDs
    - OVS bridge topology
    - Physical NICs on the path

    Args:
        vm_id: VM UUID
        host: Host (hypervisor) IP address

    Returns:
        EnvCollectionResult with VMNetworkEnv data

    Example:
        >>> result = collect_vm_network_env(
        ...     vm_id="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        ...     host="192.168.75.101"
        ... )
        >>> if result.success:
        ...     env = result.data
        ...     for nic in env.nics:
        ...         print(f"MAC: {nic.mac}, vnet: {nic.host_vnet}")
    """
    settings = get_settings()
    log = logger.bind(vm_id=vm_id, host=host)

    try:
        with SSHManager(settings.ssh) as ssh:
            collector = NetworkEnvCollector(ssh, host)
            env = collector.collect_vm_network(vm_id)

            if env is None:
                log.warning("vm_env_collection_failed")
                return EnvCollectionResult(
                    success=False,
                    host=host,
                    error=f"Failed to collect VM environment for {vm_id}",
                )

            log.info(
                "vm_env_collected",
                qemu_pid=env.qemu_pid,
                nic_count=len(env.nics),
            )

            return EnvCollectionResult(
                success=True,
                host=host,
                data=env,
            )

    except Exception as e:
        log.error("vm_env_collection_error", error=str(e))
        return EnvCollectionResult(
            success=False,
            host=host,
            error=str(e),
        )


def collect_system_network_env(
    host: str,
    port_type: str | None = None,
) -> EnvCollectionResult:
    """Collect system network environment information.

    This is an L2 layer tool for gathering system network topology including:
    - OVS internal ports (port-mgt, port-storage, etc.)
    - Bridge configurations
    - Physical NICs and bonds

    Args:
        host: Target host IP address
        port_type: Optional filter for specific port type (mgt, storage, access, vpc)

    Returns:
        EnvCollectionResult with SystemNetworkEnv data

    Example:
        >>> result = collect_system_network_env("192.168.75.101")
        >>> if result.success:
        ...     env = result.data
        ...     for port in env.ports:
        ...         print(f"Port: {port.port_name}, IP: {port.ip_address}")
    """
    settings = get_settings()
    log = logger.bind(host=host, port_type=port_type)

    try:
        with SSHManager(settings.ssh) as ssh:
            collector = NetworkEnvCollector(ssh, host)
            ports = collector.collect_system_network(port_type)

            env = SystemNetworkEnv(host=host, ports=ports)

            log.info("system_env_collected", port_count=len(ports))

            return EnvCollectionResult(
                success=True,
                host=host,
                data=env,
            )

    except Exception as e:
        log.error("system_env_collection_error", error=str(e))
        return EnvCollectionResult(
            success=False,
            host=host,
            error=str(e),
        )


def build_network_path(
    env: VMNetworkEnv | SystemNetworkEnv,
    target_env: VMNetworkEnv | SystemNetworkEnv | None = None,
) -> NetworkPath:
    """Build network path description from environment data.

    This converts raw environment data into a structured path description
    that can guide L3 measurement tool selection.

    Args:
        env: Source environment (VM or System)
        target_env: Target environment for path diagnosis (optional)

    Returns:
        NetworkPath with source/target endpoints and path segments
    """
    if isinstance(env, VMNetworkEnv):
        network_type = NetworkType.VM
        # Use first NIC by default
        nic = env.nics[0] if env.nics else None
        source = NetworkEndpoint(
            host=env.host,
            vm_id=env.vm_uuid,
            vnet=nic.host_vnet if nic else None,
            bridge=nic.ovs_bridge if nic else None,
            vhost_pid=nic.vhost_pids[0].pid if nic and nic.vhost_pids else None,
            physical_nic=nic.physical_nics[0].name if nic and nic.physical_nics else None,
        )

        # Build path segments for VM network
        segments = [
            PathSegment(name="virtio_tx", from_point="VM virtio driver", to_point="vhost-net"),
            PathSegment(name="vhost_to_tap", from_point="vhost-net", to_point="TAP device"),
            PathSegment(name="tap_to_ovs", from_point="TAP device", to_point="OVS bridge"),
            PathSegment(name="ovs_flow", from_point="OVS datapath", to_point="Physical NIC"),
            PathSegment(name="nic_tx", from_point="NIC driver", to_point="Wire"),
        ]

    else:  # SystemNetworkEnv
        network_type = NetworkType.SYSTEM
        port = env.ports[0] if env.ports else None
        source = NetworkEndpoint(
            host=env.host,
            bridge=port.ovs_bridge if port else None,
            physical_nic=port.physical_nics[0].name if port and port.physical_nics else None,
        )

        segments = [
            PathSegment(name="kernel_tx", from_point="Socket buffer", to_point="Netfilter"),
            PathSegment(name="routing", from_point="Netfilter", to_point="OVS internal port"),
            PathSegment(name="ovs_flow", from_point="OVS datapath", to_point="Physical NIC"),
            PathSegment(name="nic_tx", from_point="NIC driver", to_point="Wire"),
        ]

    # Build target endpoint if provided
    target = None
    if target_env:
        if isinstance(target_env, VMNetworkEnv):
            nic = target_env.nics[0] if target_env.nics else None
            target = NetworkEndpoint(
                host=target_env.host,
                vm_id=target_env.vm_uuid,
                vnet=nic.host_vnet if nic else None,
                bridge=nic.ovs_bridge if nic else None,
                vhost_pid=nic.vhost_pids[0].pid if nic and nic.vhost_pids else None,
                physical_nic=nic.physical_nics[0].name if nic and nic.physical_nics else None,
            )
        else:
            port = target_env.ports[0] if target_env.ports else None
            target = NetworkEndpoint(
                host=target_env.host,
                bridge=port.ovs_bridge if port else None,
                physical_nic=port.physical_nics[0].name if port and port.physical_nics else None,
            )

    return NetworkPath(
        network_type=network_type,
        source=source,
        target=target,
        path_segments=segments,
        raw_env=env,
    )
