"""Tests for GlobalInventory VM name-based identity resolution."""
import pytest
from netsherlock.config.global_inventory import GlobalInventory, HostConfig, VMConfig


@pytest.fixture
def inventory():
    """Create a test inventory with two hosts and two VMs."""
    inv = GlobalInventory.__new__(GlobalInventory)
    inv.hosts = {
        "host-31": HostConfig(
            mgmt_ip="192.168.70.31", ssh_user="smartx", ssh_key_file=None
        ),
        "host-32": HostConfig(
            mgmt_ip="192.168.70.32", ssh_user="smartx", ssh_key_file=None
        ),
    }
    inv.vms = {
        "sender-vm": VMConfig(
            uuid="uuid-sender-1234",
            host_ref="host-31",
            ssh_user="root",
            ssh_host="10.0.0.1",
            name="web-server-01",
        ),
        "receiver-vm": VMConfig(
            uuid="uuid-receiver-5678",
            host_ref="host-32",
            ssh_user="root",
            ssh_host="10.0.0.2",
            name="db-server-01",
        ),
    }
    return inv


class TestFindVmByName:

    def test_found_by_name_field(self, inventory):
        result = inventory.find_vm_by_name("web-server-01")
        assert result is not None
        key, vm = result
        assert vm.uuid == "uuid-sender-1234"

    def test_found_by_dict_key_fallback(self, inventory):
        result = inventory.find_vm_by_name("sender-vm")
        assert result is not None
        _, vm = result
        assert vm.uuid == "uuid-sender-1234"

    def test_not_found(self, inventory):
        assert inventory.find_vm_by_name("nonexistent") is None


class TestResolveVmPair:

    def test_both_resolved(self, inventory):
        ctx = inventory.resolve_vm_pair("web-server-01", "db-server-01")
        assert ctx["src_host"] == "192.168.70.31"
        assert ctx["src_vm"] == "uuid-sender-1234"
        assert ctx["dst_host"] == "192.168.70.32"
        assert ctx["dst_vm"] == "uuid-receiver-5678"

    def test_src_only(self, inventory):
        ctx = inventory.resolve_vm_pair("web-server-01", "unknown-vm")
        assert ctx["src_vm"] == "uuid-sender-1234"
        assert ctx["dst_vm"] is None

    def test_by_dict_key(self, inventory):
        """Can also resolve using the inventory dict key."""
        ctx = inventory.resolve_vm_pair("sender-vm", "receiver-vm")
        assert ctx["src_vm"] == "uuid-sender-1234"
        assert ctx["dst_vm"] == "uuid-receiver-5678"
