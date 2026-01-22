"""Minimal input configuration for diagnosis.

This module defines the MinimalInputConfig schema for manual mode diagnosis.
The configuration provides static SSH credentials and test flow IPs for nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class SSHConfig:
    """SSH connection configuration.

    Attributes:
        user: SSH username
        host: SSH host IP or hostname
        key_file: Optional path to SSH private key
    """

    user: str
    host: str
    key_file: str | None = None

    @classmethod
    def from_string(cls, ssh_str: str) -> SSHConfig:
        """Parse 'user@host' format string.

        Args:
            ssh_str: SSH connection string in format 'user@host'

        Returns:
            SSHConfig instance

        Raises:
            ValueError: If format is invalid
        """
        if "@" not in ssh_str:
            raise ValueError(f"Invalid SSH format: {ssh_str}. Expected 'user@host'")
        user, host = ssh_str.split("@", 1)
        return cls(user=user, host=host)

    def to_string(self) -> str:
        """Convert to 'user@host' format."""
        return f"{self.user}@{self.host}"


@dataclass
class NodeConfig:
    """Configuration for a single node (VM or host).

    Attributes:
        ssh: SSH connection configuration
        workdir: Remote working directory for tool deployment
        role: Node role ('vm' or 'host')
        host_ref: Reference to host node (required for VM role)
        uuid: VM UUID (required for VM role)
        test_ip: Test traffic IP (may differ from SSH IP)
    """

    ssh: SSHConfig
    workdir: str
    role: Literal["vm", "host"]
    host_ref: str | None = None
    uuid: str | None = None
    test_ip: str | None = None

    def __post_init__(self) -> None:
        """Validate node configuration."""
        if self.role == "vm":
            if not self.uuid:
                raise ValueError("uuid is required for VM nodes")
            if not self.host_ref:
                raise ValueError("host_ref is required for VM nodes")

    @property
    def ssh_string(self) -> str:
        """Get SSH connection string."""
        return self.ssh.to_string()


@dataclass
class NodePair:
    """Node pair definition for cross-node measurement.

    Attributes:
        server: Server (receiver) node name
        client: Client (sender) node name

    Note: Renamed from TestPair to avoid pytest collection warnings.
    """

    server: str
    client: str


# Backward compatibility alias
TestPair = NodePair


@dataclass
class MinimalInputConfig:
    """Minimal input configuration for diagnosis.

    This configuration defines target nodes and their SSH credentials
    for manual mode diagnosis.

    Attributes:
        nodes: Dictionary of node name to NodeConfig
        test_pairs: Optional dictionary of test pair type to TestPair
        discovery_hints: Optional hints for environment discovery
    """

    nodes: dict[str, NodeConfig] = field(default_factory=dict)
    test_pairs: dict[str, NodePair] | None = None
    discovery_hints: dict | None = None

    @classmethod
    def load(cls, path: str | Path) -> MinimalInputConfig:
        """Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            MinimalInputConfig instance

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If YAML format is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid configuration format in {path}")

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> MinimalInputConfig:
        """Create instance from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            MinimalInputConfig instance
        """
        nodes = {}
        for name, node_data in data.get("nodes", {}).items():
            ssh_str = node_data.get("ssh", "")
            ssh = SSHConfig.from_string(ssh_str)

            # Override with key_file if present
            if "ssh_key" in node_data:
                ssh.key_file = node_data["ssh_key"]

            nodes[name] = NodeConfig(
                ssh=ssh,
                workdir=node_data.get("workdir", "/tmp/netsherlock"),
                role=node_data.get("role", "host"),
                host_ref=node_data.get("host_ref"),
                uuid=node_data.get("uuid"),
                test_ip=node_data.get("test_ip"),
            )

        test_pairs = None
        if "test_pairs" in data:
            test_pairs = {
                k: NodePair(server=v["server"], client=v["client"])
                for k, v in data["test_pairs"].items()
            }

        return cls(
            nodes=nodes,
            test_pairs=test_pairs,
            discovery_hints=data.get("discovery_hints"),
        )

    def get_node(self, name: str) -> NodeConfig | None:
        """Get node configuration by name.

        Args:
            name: Node name

        Returns:
            NodeConfig if found, None otherwise
        """
        return self.nodes.get(name)

    def get_node_by_uuid(self, uuid: str) -> NodeConfig | None:
        """Find VM node by UUID.

        Args:
            uuid: VM UUID

        Returns:
            NodeConfig if found, None otherwise
        """
        for node in self.nodes.values():
            if node.uuid == uuid:
                return node
        return None

    def get_host_for_vm(self, vm_node_name: str) -> NodeConfig | None:
        """Get host node for a VM.

        Args:
            vm_node_name: Name of VM node

        Returns:
            Host NodeConfig if found, None otherwise
        """
        vm_node = self.nodes.get(vm_node_name)
        if vm_node and vm_node.host_ref:
            return self.nodes.get(vm_node.host_ref)
        return None

    def get_vm_nodes(self) -> dict[str, NodeConfig]:
        """Get all VM nodes.

        Returns:
            Dictionary of VM node name to NodeConfig
        """
        return {name: node for name, node in self.nodes.items() if node.role == "vm"}

    def get_host_nodes(self) -> dict[str, NodeConfig]:
        """Get all host nodes.

        Returns:
            Dictionary of host node name to NodeConfig
        """
        return {name: node for name, node in self.nodes.items() if node.role == "host"}

    def get_test_pair(self, pair_type: str = "vm") -> NodePair | None:
        """Get test pair by type.

        Args:
            pair_type: Type of test pair (default: 'vm')

        Returns:
            NodePair if found, None otherwise
        """
        if self.test_pairs:
            return self.test_pairs.get(pair_type)
        return None

    def get_sender_receiver_config(
        self, pair_type: str = "vm"
    ) -> tuple[NodeConfig, NodeConfig, NodeConfig, NodeConfig] | None:
        """Get full sender/receiver configuration.

        Args:
            pair_type: Type of test pair (default: 'vm')

        Returns:
            Tuple of (sender_vm, sender_host, receiver_vm, receiver_host)
            or None if incomplete
        """
        test_pair = self.get_test_pair(pair_type)
        if not test_pair:
            return None

        sender_vm = self.get_node(test_pair.client)
        receiver_vm = self.get_node(test_pair.server)

        if not sender_vm or not receiver_vm:
            return None

        sender_host = self.get_host_for_vm(test_pair.client)
        receiver_host = self.get_host_for_vm(test_pair.server)

        if not sender_host or not receiver_host:
            return None

        return (sender_vm, sender_host, receiver_vm, receiver_host)

    def validate(self) -> list[str]:
        """Validate configuration completeness.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check all VM nodes have host_ref pointing to valid host
        for name, node in self.nodes.items():
            if node.role == "vm":
                if not node.host_ref:
                    errors.append(f"VM node '{name}' missing host_ref")
                elif node.host_ref not in self.nodes:
                    errors.append(
                        f"VM node '{name}' references non-existent host '{node.host_ref}'"
                    )
                elif self.nodes[node.host_ref].role != "host":
                    errors.append(
                        f"VM node '{name}' host_ref '{node.host_ref}' is not a host node"
                    )

        # Check test_pairs reference valid nodes
        if self.test_pairs:
            for pair_type, pair in self.test_pairs.items():
                if pair.client not in self.nodes:
                    errors.append(
                        f"Test pair '{pair_type}' client '{pair.client}' not found"
                    )
                if pair.server not in self.nodes:
                    errors.append(
                        f"Test pair '{pair_type}' server '{pair.server}' not found"
                    )

        return errors

    def to_dict(self) -> dict:
        """Convert to dictionary (for YAML serialization).

        Returns:
            Configuration as dictionary
        """
        result = {
            "nodes": {
                name: {
                    "ssh": node.ssh_string,
                    "workdir": node.workdir,
                    "role": node.role,
                    **({"host_ref": node.host_ref} if node.host_ref else {}),
                    **({"uuid": node.uuid} if node.uuid else {}),
                    **({"test_ip": node.test_ip} if node.test_ip else {}),
                    **({"ssh_key": node.ssh.key_file} if node.ssh.key_file else {}),
                }
                for name, node in self.nodes.items()
            }
        }

        if self.test_pairs:
            result["test_pairs"] = {
                k: {"server": v.server, "client": v.client}
                for k, v in self.test_pairs.items()
            }

        if self.discovery_hints:
            result["discovery_hints"] = self.discovery_hints

        return result
