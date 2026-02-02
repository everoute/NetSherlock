"""Tests for GlobalInventory."""

import tempfile
from pathlib import Path

import pytest

from netsherlock.config.global_inventory import (
    GlobalInventory,
    HostConfig,
    VMConfig,
)


class TestHostConfig:
    """Tests for HostConfig."""

    def test_create_host_config(self):
        """Create host configuration."""
        host = HostConfig(
            mgmt_ip="192.168.75.101",
            ssh_user="smartx",
            ssh_key_file="/root/.ssh/host_key",
            network_types=["mgt", "storage"],
        )
        assert host.mgmt_ip == "192.168.75.101"
        assert host.ssh_user == "smartx"
        assert host.ssh_key_file == "/root/.ssh/host_key"
        assert "mgt" in host.network_types

    def test_host_config_minimal(self):
        """Create minimal host configuration."""
        host = HostConfig(mgmt_ip="192.168.1.1", ssh_user="root")
        assert host.ssh_key_file is None
        assert host.network_types == []


class TestVMConfig:
    """Tests for VMConfig."""

    def test_create_vm_config(self):
        """Create VM configuration."""
        vm = VMConfig(
            uuid="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            host_ref="host-sender",
            ssh_user="root",
            ssh_host="192.168.2.100",
            ssh_key_file="/root/.ssh/vm_key",
            name="web-server-01",
        )
        assert vm.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"
        assert vm.host_ref == "host-sender"
        assert vm.name == "web-server-01"

    def test_vm_config_minimal(self):
        """Create minimal VM configuration."""
        vm = VMConfig(
            uuid="test-uuid",
            host_ref="host-1",
            ssh_user="root",
            ssh_host="10.0.0.1",
        )
        assert vm.ssh_key_file is None
        assert vm.name == ""


class TestGlobalInventory:
    """Tests for GlobalInventory."""

    @pytest.fixture
    def sample_yaml_content(self):
        """Sample YAML content for testing."""
        return """
hosts:
  host-192-168-75-101:
    mgmt_ip: "192.168.75.101"
    ssh:
      user: "smartx"
      key_file: "/root/.ssh/host_key"
    network_types:
      - mgt
      - storage
      - access

  host-192-168-75-102:
    mgmt_ip: "192.168.75.102"
    ssh:
      user: "smartx"
      key_file: "/root/.ssh/host_key"
    network_types:
      - mgt
      - storage

vms:
  vm-ae6aa164:
    name: "web-server-01"
    uuid: "ae6aa164-604c-4cb0-84b8-2dea034307f1"
    host_ref: "host-192-168-75-101"
    ssh:
      user: "root"
      host: "192.168.2.100"
      key_file: "/root/.ssh/vm_key"

  vm-be7bb275:
    name: "db-server-01"
    uuid: "be7bb275-715d-5dc1-95c9-3efb045418g2"
    host_ref: "host-192-168-75-102"
    ssh:
      user: "root"
      host: "192.168.2.101"
      key_file: "/root/.ssh/vm_key"
"""

    @pytest.fixture
    def sample_inventory_file(self, sample_yaml_content):
        """Create temporary inventory file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(sample_yaml_content)
            return Path(f.name)

    def test_load_from_yaml(self, sample_inventory_file):
        """Load inventory from YAML file."""
        inventory = GlobalInventory.load(sample_inventory_file)

        assert len(inventory.hosts) == 2
        assert len(inventory.vms) == 2
        assert "host-192-168-75-101" in inventory.hosts
        assert "vm-ae6aa164" in inventory.vms

    def test_load_file_not_found(self):
        """Load raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            GlobalInventory.load("/nonexistent/path.yaml")

    def test_find_host_by_ip(self, sample_inventory_file):
        """Find host by management IP."""
        inventory = GlobalInventory.load(sample_inventory_file)

        result = inventory.find_host_by_ip("192.168.75.101")
        assert result is not None
        name, host = result
        assert name == "host-192-168-75-101"
        assert host.ssh_user == "smartx"

        assert inventory.find_host_by_ip("10.0.0.99") is None

    def test_find_vm_by_uuid(self, sample_inventory_file):
        """Find VM by UUID."""
        inventory = GlobalInventory.load(sample_inventory_file)

        result = inventory.find_vm_by_uuid("ae6aa164-604c-4cb0-84b8-2dea034307f1")
        assert result is not None
        name, vm = result
        assert name == "vm-ae6aa164"
        assert vm.name == "web-server-01"

        assert inventory.find_vm_by_uuid("nonexistent-uuid") is None

    def test_build_minimal_input_cross_node_vm(self, sample_inventory_file):
        """Build MinimalInputConfig for cross-node VM scenario."""
        inventory = GlobalInventory.load(sample_inventory_file)

        config = inventory.build_minimal_input(
            src_host_ip="192.168.75.101",
            src_vm_uuid="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host_ip="192.168.75.102",
            dst_vm_uuid="be7bb275-715d-5dc1-95c9-3efb045418g2",
            src_test_ip="10.0.0.1",
            dst_test_ip="10.0.0.2",
        )

        assert len(config.nodes) == 4
        assert "host-sender" in config.nodes
        assert "host-receiver" in config.nodes
        assert "vm-sender" in config.nodes
        assert "vm-receiver" in config.nodes

        # Check test_pairs created
        assert config.test_pairs is not None
        assert "vm" in config.test_pairs
        assert config.test_pairs["vm"].server == "vm-receiver"
        assert config.test_pairs["vm"].client == "vm-sender"

        # Check node details — test_ip comes from parameter, not VMConfig
        sender_vm = config.get_node("vm-sender")
        assert sender_vm.test_ip == "10.0.0.1"
        assert sender_vm.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"

    def test_build_minimal_input_single_host(self, sample_inventory_file):
        """Build MinimalInputConfig for single host."""
        inventory = GlobalInventory.load(sample_inventory_file)

        config = inventory.build_minimal_input(src_host_ip="192.168.75.101")

        assert len(config.nodes) == 1
        assert "host-sender" in config.nodes
        assert config.test_pairs is None

    def test_build_minimal_input_host_not_found(self, sample_inventory_file):
        """Build MinimalInputConfig raises for missing host."""
        inventory = GlobalInventory.load(sample_inventory_file)

        with pytest.raises(ValueError, match="not found in inventory"):
            inventory.build_minimal_input(src_host_ip="10.0.0.99")

    def test_build_minimal_input_vm_not_found(self, sample_inventory_file):
        """Build MinimalInputConfig raises for missing VM."""
        inventory = GlobalInventory.load(sample_inventory_file)

        with pytest.raises(ValueError, match="not found in inventory"):
            inventory.build_minimal_input(
                src_host_ip="192.168.75.101",
                src_vm_uuid="nonexistent-uuid",
            )

    def test_validate_valid_inventory(self, sample_inventory_file):
        """Validate valid inventory."""
        inventory = GlobalInventory.load(sample_inventory_file)
        errors = inventory.validate()
        assert len(errors) == 0

    def test_validate_invalid_host_ref(self):
        """Validate detects invalid host_ref."""
        inventory = GlobalInventory(
            hosts={
                "host-1": HostConfig(mgmt_ip="192.168.1.1", ssh_user="root"),
            },
            vms={
                "vm-1": VMConfig(
                    uuid="test-uuid",
                    host_ref="nonexistent-host",
                    ssh_user="root",
                    ssh_host="10.0.0.1",
                ),
            },
        )
        errors = inventory.validate()
        assert len(errors) == 1
        assert "non-existent host" in errors[0]

    def test_validate_duplicate_uuids(self):
        """Validate detects duplicate UUIDs."""
        inventory = GlobalInventory(
            hosts={
                "host-1": HostConfig(mgmt_ip="192.168.1.1", ssh_user="root"),
            },
            vms={
                "vm-1": VMConfig(
                    uuid="same-uuid",
                    host_ref="host-1",
                    ssh_user="root",
                    ssh_host="10.0.0.1",
                ),
                "vm-2": VMConfig(
                    uuid="same-uuid",
                    host_ref="host-1",
                    ssh_user="root",
                    ssh_host="10.0.0.2",
                ),
            },
        )
        errors = inventory.validate()
        assert any("Duplicate VM UUIDs" in e for e in errors)

    def test_validate_duplicate_mgmt_ips(self):
        """Validate detects duplicate management IPs."""
        inventory = GlobalInventory(
            hosts={
                "host-1": HostConfig(mgmt_ip="192.168.1.1", ssh_user="root"),
                "host-2": HostConfig(mgmt_ip="192.168.1.1", ssh_user="admin"),
            },
            vms={},
        )
        errors = inventory.validate()
        assert any("Duplicate host management IPs" in e for e in errors)

    def test_to_dict(self, sample_inventory_file):
        """Convert to dictionary."""
        inventory = GlobalInventory.load(sample_inventory_file)
        d = inventory.to_dict()

        assert "hosts" in d
        assert "vms" in d
        assert len(d["hosts"]) == 2
        assert len(d["vms"]) == 2


class TestGlobalInventoryEdgeCases:
    """Edge case tests for GlobalInventory."""

    def test_empty_inventory(self):
        """Empty inventory."""
        inventory = GlobalInventory()
        assert len(inventory.hosts) == 0
        assert len(inventory.vms) == 0

    def test_hosts_only_inventory(self):
        """Inventory with only hosts."""
        inventory = GlobalInventory(
            hosts={
                "host-1": HostConfig(mgmt_ip="192.168.1.1", ssh_user="root"),
            },
            vms={},
        )
        config = inventory.build_minimal_input(src_host_ip="192.168.1.1")
        assert len(config.nodes) == 1

    def test_build_minimal_input_single_vm(self):
        """Build MinimalInputConfig for single VM (no destination)."""
        inventory = GlobalInventory(
            hosts={
                "host-1": HostConfig(mgmt_ip="192.168.1.1", ssh_user="root"),
            },
            vms={
                "vm-1": VMConfig(
                    uuid="test-uuid",
                    host_ref="host-1",
                    ssh_user="root",
                    ssh_host="10.0.0.1",
                    name="test-vm-01",
                ),
            },
        )

        config = inventory.build_minimal_input(
            src_host_ip="192.168.1.1",
            src_vm_uuid="test-uuid",
        )

        assert len(config.nodes) == 2
        assert "host-sender" in config.nodes
        assert "vm-sender" in config.nodes
        assert config.test_pairs is None  # No receiver
