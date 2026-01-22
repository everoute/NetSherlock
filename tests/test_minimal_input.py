"""Tests for MinimalInputConfig schema."""

import tempfile
from pathlib import Path

import pytest

from netsherlock.schemas.minimal_input import (
    MinimalInputConfig,
    NodeConfig,
    SSHConfig,
    TestPair,
)


class TestSSHConfig:
    """Tests for SSHConfig."""

    def test_from_string_valid(self):
        """Parse valid SSH string."""
        ssh = SSHConfig.from_string("root@192.168.1.10")
        assert ssh.user == "root"
        assert ssh.host == "192.168.1.10"

    def test_from_string_invalid(self):
        """Invalid SSH string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid SSH format"):
            SSHConfig.from_string("invalid")

    def test_to_string(self):
        """Convert to SSH string."""
        ssh = SSHConfig(user="admin", host="10.0.0.1")
        assert ssh.to_string() == "admin@10.0.0.1"

    def test_with_key_file(self):
        """SSHConfig with key file."""
        ssh = SSHConfig(user="root", host="host.local", key_file="/root/.ssh/id_rsa")
        assert ssh.key_file == "/root/.ssh/id_rsa"


class TestNodeConfig:
    """Tests for NodeConfig."""

    def test_vm_node_requires_uuid(self):
        """VM node requires uuid."""
        with pytest.raises(ValueError, match="uuid is required"):
            NodeConfig(
                ssh=SSHConfig(user="root", host="10.0.0.1"),
                workdir="/tmp",
                role="vm",
                host_ref="host-1",
            )

    def test_vm_node_requires_host_ref(self):
        """VM node requires host_ref."""
        with pytest.raises(ValueError, match="host_ref is required"):
            NodeConfig(
                ssh=SSHConfig(user="root", host="10.0.0.1"),
                workdir="/tmp",
                role="vm",
                uuid="test-uuid",
            )

    def test_valid_vm_node(self):
        """Valid VM node configuration."""
        node = NodeConfig(
            ssh=SSHConfig(user="root", host="10.0.0.1"),
            workdir="/tmp",
            role="vm",
            host_ref="host-1",
            uuid="test-uuid",
            test_ip="192.168.1.1",
        )
        assert node.role == "vm"
        assert node.uuid == "test-uuid"
        assert node.host_ref == "host-1"
        assert node.test_ip == "192.168.1.1"

    def test_valid_host_node(self):
        """Valid host node configuration."""
        node = NodeConfig(
            ssh=SSHConfig(user="admin", host="192.168.75.101"),
            workdir="/tmp/netsherlock",
            role="host",
        )
        assert node.role == "host"
        assert node.uuid is None
        assert node.host_ref is None

    def test_ssh_string_property(self):
        """Get SSH connection string."""
        node = NodeConfig(
            ssh=SSHConfig(user="root", host="10.0.0.1"),
            workdir="/tmp",
            role="host",
        )
        assert node.ssh_string == "root@10.0.0.1"


class TestTestPair:
    """Tests for TestPair."""

    def test_create_test_pair(self):
        """Create test pair."""
        pair = TestPair(server="vm-receiver", client="vm-sender")
        assert pair.server == "vm-receiver"
        assert pair.client == "vm-sender"


class TestMinimalInputConfig:
    """Tests for MinimalInputConfig."""

    @pytest.fixture
    def sample_yaml_content(self):
        """Sample YAML content for testing."""
        return """
nodes:
  vm-sender:
    ssh: "root@192.168.2.100"
    workdir: "/tmp/netsherlock"
    role: "vm"
    host_ref: "host-sender"
    uuid: "ae6aa164-604c-4cb0-84b8-2dea034307f1"
    test_ip: "10.0.0.1"

  vm-receiver:
    ssh: "root@192.168.2.101"
    workdir: "/tmp/netsherlock"
    role: "vm"
    host_ref: "host-receiver"
    uuid: "be7bb275-715d-5dc1-95c9-3efb045418g2"
    test_ip: "10.0.0.2"

  host-sender:
    ssh: "smartx@192.168.75.101"
    workdir: "/tmp/netsherlock"
    role: "host"

  host-receiver:
    ssh: "smartx@192.168.75.102"
    workdir: "/tmp/netsherlock"
    role: "host"

test_pairs:
  vm:
    server: "vm-receiver"
    client: "vm-sender"

discovery_hints:
  internal_port_type: "mgt"
"""

    @pytest.fixture
    def sample_config_file(self, sample_yaml_content):
        """Create temporary config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(sample_yaml_content)
            return Path(f.name)

    def test_load_from_yaml(self, sample_config_file):
        """Load configuration from YAML file."""
        config = MinimalInputConfig.load(sample_config_file)

        assert len(config.nodes) == 4
        assert "vm-sender" in config.nodes
        assert "vm-receiver" in config.nodes
        assert "host-sender" in config.nodes
        assert "host-receiver" in config.nodes

    def test_load_file_not_found(self):
        """Load raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            MinimalInputConfig.load("/nonexistent/path.yaml")

    def test_get_node(self, sample_config_file):
        """Get node by name."""
        config = MinimalInputConfig.load(sample_config_file)

        node = config.get_node("vm-sender")
        assert node is not None
        assert node.role == "vm"
        assert node.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"

        assert config.get_node("nonexistent") is None

    def test_get_node_by_uuid(self, sample_config_file):
        """Get node by UUID."""
        config = MinimalInputConfig.load(sample_config_file)

        node = config.get_node_by_uuid("ae6aa164-604c-4cb0-84b8-2dea034307f1")
        assert node is not None
        assert node.test_ip == "10.0.0.1"

        assert config.get_node_by_uuid("nonexistent-uuid") is None

    def test_get_host_for_vm(self, sample_config_file):
        """Get host node for VM."""
        config = MinimalInputConfig.load(sample_config_file)

        host = config.get_host_for_vm("vm-sender")
        assert host is not None
        assert host.role == "host"

        assert config.get_host_for_vm("nonexistent") is None

    def test_get_vm_nodes(self, sample_config_file):
        """Get all VM nodes."""
        config = MinimalInputConfig.load(sample_config_file)

        vm_nodes = config.get_vm_nodes()
        assert len(vm_nodes) == 2
        assert "vm-sender" in vm_nodes
        assert "vm-receiver" in vm_nodes

    def test_get_host_nodes(self, sample_config_file):
        """Get all host nodes."""
        config = MinimalInputConfig.load(sample_config_file)

        host_nodes = config.get_host_nodes()
        assert len(host_nodes) == 2
        assert "host-sender" in host_nodes
        assert "host-receiver" in host_nodes

    def test_get_test_pair(self, sample_config_file):
        """Get test pair."""
        config = MinimalInputConfig.load(sample_config_file)

        pair = config.get_test_pair("vm")
        assert pair is not None
        assert pair.server == "vm-receiver"
        assert pair.client == "vm-sender"

        assert config.get_test_pair("nonexistent") is None

    def test_get_sender_receiver_config(self, sample_config_file):
        """Get full sender/receiver configuration."""
        config = MinimalInputConfig.load(sample_config_file)

        result = config.get_sender_receiver_config("vm")
        assert result is not None

        sender_vm, sender_host, receiver_vm, receiver_host = result
        assert sender_vm.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"
        assert sender_host.role == "host"
        assert receiver_vm.uuid == "be7bb275-715d-5dc1-95c9-3efb045418g2"
        assert receiver_host.role == "host"

    def test_validate_valid_config(self, sample_config_file):
        """Validate valid configuration."""
        config = MinimalInputConfig.load(sample_config_file)
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_missing_host_ref(self):
        """Validate detects missing host_ref."""
        config = MinimalInputConfig(
            nodes={
                "vm-1": NodeConfig(
                    ssh=SSHConfig(user="root", host="10.0.0.1"),
                    workdir="/tmp",
                    role="vm",
                    uuid="test-uuid",
                    host_ref="nonexistent-host",
                ),
            }
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "non-existent host" in errors[0]

    def test_validate_invalid_test_pair(self):
        """Validate detects invalid test pair reference."""
        config = MinimalInputConfig(
            nodes={
                "host-1": NodeConfig(
                    ssh=SSHConfig(user="root", host="10.0.0.1"),
                    workdir="/tmp",
                    role="host",
                ),
            },
            test_pairs={"vm": TestPair(server="nonexistent", client="also-nonexistent")},
        )
        errors = config.validate()
        assert len(errors) == 2

    def test_to_dict(self, sample_config_file):
        """Convert to dictionary."""
        config = MinimalInputConfig.load(sample_config_file)
        d = config.to_dict()

        assert "nodes" in d
        assert "test_pairs" in d
        assert "discovery_hints" in d
        assert len(d["nodes"]) == 4

    def test_discovery_hints(self, sample_config_file):
        """Discovery hints are loaded."""
        config = MinimalInputConfig.load(sample_config_file)
        assert config.discovery_hints is not None
        assert config.discovery_hints.get("internal_port_type") == "mgt"


class TestMinimalInputConfigEdgeCases:
    """Edge case tests for MinimalInputConfig."""

    def test_empty_config(self):
        """Empty configuration."""
        config = MinimalInputConfig()
        assert len(config.nodes) == 0
        assert config.test_pairs is None

    def test_host_only_config(self):
        """Configuration with only host nodes."""
        config = MinimalInputConfig(
            nodes={
                "host-1": NodeConfig(
                    ssh=SSHConfig(user="root", host="192.168.1.1"),
                    workdir="/tmp",
                    role="host",
                ),
            }
        )
        assert len(config.get_host_nodes()) == 1
        assert len(config.get_vm_nodes()) == 0

    def test_incomplete_test_pair(self):
        """Get sender/receiver with missing nodes."""
        config = MinimalInputConfig(
            nodes={
                "vm-sender": NodeConfig(
                    ssh=SSHConfig(user="root", host="10.0.0.1"),
                    workdir="/tmp",
                    role="vm",
                    host_ref="host-1",
                    uuid="test-uuid",
                ),
                "host-1": NodeConfig(
                    ssh=SSHConfig(user="root", host="192.168.1.1"),
                    workdir="/tmp",
                    role="host",
                ),
            },
            test_pairs={"vm": TestPair(server="vm-receiver", client="vm-sender")},
        )
        # Missing vm-receiver
        result = config.get_sender_receiver_config("vm")
        assert result is None
