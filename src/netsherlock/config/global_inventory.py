"""Global inventory configuration for automatic mode.

This module defines the GlobalInventory schema that holds pre-configured
information about all managed nodes and VMs in the environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from netsherlock.schemas.minimal_input import (
    MinimalInputConfig,
    NodeConfig,
    NodePair,
    SSHConfig,
)


@dataclass
class HostConfig:
    """Host configuration in global inventory.

    Attributes:
        mgmt_ip: Management IP address
        ssh_user: SSH username
        ssh_key_file: Optional SSH private key path
        network_types: List of network types available on host
    """

    mgmt_ip: str
    ssh_user: str
    ssh_key_file: str | None = None
    network_types: list[str] = field(default_factory=list)


@dataclass
class VMConfig:
    """VM configuration in global inventory.

    Attributes:
        uuid: VM UUID
        host_ref: Reference to host in inventory
        ssh_user: SSH username for VM
        ssh_host: SSH host/IP for VM
        ssh_key_file: Optional SSH private key path
        name: VM display name for monitoring system lookup
    """

    uuid: str
    host_ref: str
    ssh_user: str
    ssh_host: str
    ssh_key_file: str | None = None
    name: str = ""


@dataclass
class GlobalInventory:
    """Global asset inventory for automatic mode.

    This contains pre-configured information about all managed nodes
    and VMs. When an alert is received (L1), the inventory is used
    to construct a MinimalInputConfig for the diagnosis.

    Attributes:
        hosts: Dictionary of host name to HostConfig
        vms: Dictionary of VM name to VMConfig
    """

    hosts: dict[str, HostConfig] = field(default_factory=dict)
    vms: dict[str, VMConfig] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> GlobalInventory:
        """Load inventory from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            GlobalInventory instance

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If YAML format is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Inventory file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid inventory format in {path}")

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> GlobalInventory:
        """Create instance from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            GlobalInventory instance
        """
        hosts = {}
        for name, h in data.get("hosts", {}).items():
            hosts[name] = HostConfig(
                mgmt_ip=h["mgmt_ip"],
                ssh_user=h.get("ssh", {}).get("user", "root"),
                ssh_key_file=h.get("ssh", {}).get("key_file"),
                network_types=h.get("network_types", []),
            )

        vms = {}
        for name, v in data.get("vms", {}).items():
            vms[name] = VMConfig(
                uuid=v["uuid"],
                host_ref=v["host_ref"],
                ssh_user=v.get("ssh", {}).get("user", "root"),
                ssh_host=v.get("ssh", {}).get("host", ""),
                ssh_key_file=v.get("ssh", {}).get("key_file"),
                name=v.get("name", name),
            )

        return cls(hosts=hosts, vms=vms)

    def find_host_by_ip(self, ip: str) -> tuple[str, HostConfig] | None:
        """Find host by management IP.

        Args:
            ip: Management IP address

        Returns:
            Tuple of (host_name, HostConfig) if found, None otherwise
        """
        for name, host in self.hosts.items():
            if host.mgmt_ip == ip:
                return (name, host)
        return None

    def find_vm_by_uuid(self, uuid: str) -> tuple[str, VMConfig] | None:
        """Find VM by UUID.

        Args:
            uuid: VM UUID

        Returns:
            Tuple of (vm_name, VMConfig) if found, None otherwise
        """
        for name, vm in self.vms.items():
            if vm.uuid == uuid:
                return (name, vm)
        return None

    def find_host_for_vm(self, vm_uuid: str) -> tuple[str, HostConfig] | None:
        """Find host that runs a VM.

        Args:
            vm_uuid: VM UUID

        Returns:
            Tuple of (host_name, HostConfig) if found, None otherwise
        """
        vm_result = self.find_vm_by_uuid(vm_uuid)
        if not vm_result:
            return None
        _, vm_config = vm_result
        host_config = self.hosts.get(vm_config.host_ref)
        if host_config is None:
            return None
        return vm_config.host_ref, host_config

    def find_vm_by_name(self, name: str) -> tuple[str, VMConfig] | None:
        """Find VM by display name or inventory key.

        Matches against VMConfig.name field first.
        Falls back to matching against the inventory dict key.
        """
        for key, vm in self.vms.items():
            if vm.name == name:
                return (key, vm)
        # Fallback: match by dict key
        if name in self.vms:
            return (name, self.vms[name])
        return None

    def resolve_vm_pair(
        self,
        src_vm_name: str,
        dst_vm_name: str,
    ) -> dict[str, str | None]:
        """Resolve a pair of VM names to UUIDs and host management IPs.

        Core Identity Resolver for the Generic source adapter.
        Test IPs are NOT resolved here — they come from the alert itself.
        """
        result: dict[str, str | None] = {
            "src_host": None, "src_vm": None,
            "dst_host": None, "dst_vm": None,
        }

        for prefix, vm_name in [("src", src_vm_name), ("dst", dst_vm_name)]:
            vm_result = self.find_vm_by_name(vm_name)
            if vm_result:
                _, vm = vm_result
                result[f"{prefix}_vm"] = vm.uuid
                host_cfg = self.hosts.get(vm.host_ref)
                if host_cfg:
                    result[f"{prefix}_host"] = host_cfg.mgmt_ip

        return result

    def build_minimal_input(
        self,
        src_host_ip: str,
        src_vm_uuid: str | None = None,
        dst_host_ip: str | None = None,
        dst_vm_uuid: str | None = None,
        src_test_ip: str | None = None,
        dst_test_ip: str | None = None,
    ) -> MinimalInputConfig:
        """Build MinimalInputConfig from L1 alert information.

        This is the core method for automatic mode. Given L1 alert data
        (host IPs and VM UUIDs), it looks up the global inventory and
        constructs the MinimalInputConfig needed for diagnosis.

        Args:
            src_host_ip: Source host management IP
            src_vm_uuid: Source VM UUID (optional)
            dst_host_ip: Destination host management IP (optional)
            dst_vm_uuid: Destination VM UUID (optional)
            src_test_ip: Source test/data-plane IP from alert (optional)
            dst_test_ip: Destination test/data-plane IP from alert (optional)

        Returns:
            MinimalInputConfig for the diagnosis

        Raises:
            ValueError: If required nodes not found in inventory
        """
        nodes: dict[str, NodeConfig] = {}

        # Source host
        src_host_result = self.find_host_by_ip(src_host_ip)
        if src_host_result:
            host_name, host_cfg = src_host_result
            nodes["host-sender"] = NodeConfig(
                ssh=SSHConfig(
                    user=host_cfg.ssh_user,
                    host=host_cfg.mgmt_ip,
                    key_file=host_cfg.ssh_key_file,
                ),
                workdir="/tmp/netsherlock",
                role="host",
            )
        else:
            raise ValueError(f"Source host {src_host_ip} not found in inventory")

        # Source VM
        if src_vm_uuid:
            vm_result = self.find_vm_by_uuid(src_vm_uuid)
            if vm_result:
                _, vm_cfg = vm_result
                nodes["vm-sender"] = NodeConfig(
                    ssh=SSHConfig(
                        user=vm_cfg.ssh_user,
                        host=vm_cfg.ssh_host,
                        key_file=vm_cfg.ssh_key_file,
                    ),
                    workdir="/tmp/netsherlock",
                    role="vm",
                    host_ref="host-sender",
                    uuid=vm_cfg.uuid,
                    test_ip=src_test_ip,
                )
            else:
                raise ValueError(f"Source VM {src_vm_uuid} not found in inventory")

        # Destination host
        if dst_host_ip:
            dst_host_result = self.find_host_by_ip(dst_host_ip)
            if dst_host_result:
                host_name, host_cfg = dst_host_result
                nodes["host-receiver"] = NodeConfig(
                    ssh=SSHConfig(
                        user=host_cfg.ssh_user,
                        host=host_cfg.mgmt_ip,
                        key_file=host_cfg.ssh_key_file,
                    ),
                    workdir="/tmp/netsherlock",
                    role="host",
                )
            else:
                raise ValueError(f"Destination host {dst_host_ip} not found in inventory")

        # Destination VM
        if dst_vm_uuid:
            vm_result = self.find_vm_by_uuid(dst_vm_uuid)
            if vm_result:
                _, vm_cfg = vm_result
                nodes["vm-receiver"] = NodeConfig(
                    ssh=SSHConfig(
                        user=vm_cfg.ssh_user,
                        host=vm_cfg.ssh_host,
                        key_file=vm_cfg.ssh_key_file,
                    ),
                    workdir="/tmp/netsherlock",
                    role="vm",
                    host_ref="host-receiver",
                    uuid=vm_cfg.uuid,
                    test_ip=dst_test_ip,
                )
            else:
                raise ValueError(f"Destination VM {dst_vm_uuid} not found in inventory")

        # Build test_pairs if we have sender and receiver VMs
        test_pairs = None
        if "vm-sender" in nodes and "vm-receiver" in nodes:
            test_pairs = {"vm": NodePair(server="vm-receiver", client="vm-sender")}

        return MinimalInputConfig(nodes=nodes, test_pairs=test_pairs)

    def validate(self) -> list[str]:
        """Validate inventory configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check all VM host_refs point to valid hosts
        for vm_name, vm in self.vms.items():
            if vm.host_ref not in self.hosts:
                errors.append(
                    f"VM '{vm_name}' references non-existent host '{vm.host_ref}'"
                )

        # Check for duplicate UUIDs
        uuids = [vm.uuid for vm in self.vms.values()]
        if len(uuids) != len(set(uuids)):
            errors.append("Duplicate VM UUIDs found in inventory")

        # Check for duplicate management IPs
        mgmt_ips = [host.mgmt_ip for host in self.hosts.values()]
        if len(mgmt_ips) != len(set(mgmt_ips)):
            errors.append("Duplicate host management IPs found in inventory")

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization.

        Returns:
            Inventory as dictionary
        """
        return {
            "hosts": {
                name: {
                    "mgmt_ip": host.mgmt_ip,
                    "ssh": {
                        "user": host.ssh_user,
                        **({"key_file": host.ssh_key_file} if host.ssh_key_file else {}),
                    },
                    **({"network_types": host.network_types} if host.network_types else {}),
                }
                for name, host in self.hosts.items()
            },
            "vms": {
                name: {
                    "uuid": vm.uuid,
                    "host_ref": vm.host_ref,
                    "ssh": {
                        "user": vm.ssh_user,
                        "host": vm.ssh_host,
                        **({"key_file": vm.ssh_key_file} if vm.ssh_key_file else {}),
                    },
                    **({"name": vm.name} if vm.name else {}),
                }
                for name, vm in self.vms.items()
            },
        }
