"""Tests for L2 environment collection tools.

Tests for NetworkEnvCollector class and related functions.
"""

import pytest
from unittest.mock import MagicMock, patch

from netsherlock.tools.l2_environment import (
    NetworkEnvCollector,
    EnvCollectionResult,
    build_network_path,
)
from netsherlock.schemas.environment import (
    VMNetworkEnv,
    VMNicInfo,
    VhostInfo,
    PhysicalNIC,
    SystemNetworkEnv,
    SystemNetworkInfo,
    NetworkType,
)


@pytest.fixture
def mock_ssh_manager():
    """Create a mock SSH manager."""
    ssh = MagicMock()
    return ssh


@pytest.fixture
def collector(mock_ssh_manager):
    """Create a NetworkEnvCollector with mock SSH."""
    return NetworkEnvCollector(mock_ssh_manager, "192.168.75.101")


class TestNetworkEnvCollector:
    """Tests for NetworkEnvCollector class."""

    def test_init(self, mock_ssh_manager):
        """Test collector initialization."""
        collector = NetworkEnvCollector(mock_ssh_manager, "192.168.75.101")
        assert collector.host == "192.168.75.101"
        assert collector.ssh == mock_ssh_manager
        assert collector._bridge_nics_cache == {}

    def test_execute_regular_command(self, collector, mock_ssh_manager):
        """Test _execute without sudo."""
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        stdout, stderr, code = collector._execute("ls -la")

        mock_ssh_manager.execute.assert_called_once_with("192.168.75.101", "ls -la")
        assert stdout == "output"
        assert stderr == ""
        assert code == 0

    def test_execute_with_sudo(self, collector, mock_ssh_manager):
        """Test _execute with sudo."""
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        collector._execute("ovs-vsctl show", sudo=True)

        mock_ssh_manager.execute.assert_called_once_with(
            "192.168.75.101", "sudo ovs-vsctl show"
        )

    def test_get_ovs_internal_ports(self, collector, mock_ssh_manager):
        """Test getting OVS internal ports."""
        mock_result = MagicMock()
        mock_result.stdout = """
        Bridge "br-mgt"
            Port "port-mgt"
                Interface "port-mgt"
                    type: internal
            Port "vnet0"
                Interface "vnet0"
        Bridge "br-access"
            Port "port-access"
                Interface "port-access"
                    type: internal
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ports = collector.get_ovs_internal_ports()

        assert len(ports) == 2
        assert ("port-mgt", "br-mgt") in ports
        assert ("port-access", "br-access") in ports

    def test_get_ovs_internal_ports_empty(self, collector, mock_ssh_manager):
        """Test getting OVS internal ports with no ports."""
        mock_result = MagicMock()
        mock_result.stdout = """
        Bridge "br-mgt"
            Port "vnet0"
                Interface "vnet0"
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ports = collector.get_ovs_internal_ports()

        assert len(ports) == 0

    def test_get_port_ip(self, collector, mock_ssh_manager):
        """Test getting port IP address."""
        mock_result = MagicMock()
        mock_result.stdout = """
2: port-mgt: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    inet 192.168.75.101/24 brd 192.168.75.255 scope global port-mgt
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ip = collector.get_port_ip("port-mgt")

        assert ip == "192.168.75.101"

    def test_get_port_ip_not_found(self, collector, mock_ssh_manager):
        """Test getting port IP when not found."""
        mock_result = MagicMock()
        mock_result.stdout = """
2: port-mgt: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
    link/ether 00:11:22:33:44:55 brd ff:ff:ff:ff:ff:ff
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ip = collector.get_port_ip("port-mgt")

        assert ip == ""

    def test_get_port_ip_command_fails(self, collector, mock_ssh_manager):
        """Test getting port IP when command fails."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "interface not found"
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        ip = collector.get_port_ip("nonexistent")

        assert ip == ""

    def test_get_bridge_ports(self, collector, mock_ssh_manager):
        """Test getting bridge ports."""
        mock_result = MagicMock()
        mock_result.stdout = "vnet0\nvnet1\nport-mgt\nbond0"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ports = collector.get_bridge_ports("br-mgt")

        assert ports == ["vnet0", "vnet1", "port-mgt", "bond0"]

    def test_get_bridge_ports_empty(self, collector, mock_ssh_manager):
        """Test getting bridge ports when empty."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        ports = collector.get_bridge_ports("br-empty")

        assert ports == []

    def test_get_patch_peer_bridge_exists(self, collector, mock_ssh_manager):
        """Test finding peer bridge when it exists."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        peer = collector.get_patch_peer_bridge("br-access")

        assert peer == "br-access-uplink"

    def test_get_patch_peer_bridge_not_exists(self, collector, mock_ssh_manager):
        """Test finding peer bridge when it doesn't exist."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 2  # Bridge not found
        mock_ssh_manager.execute.return_value = mock_result

        peer = collector.get_patch_peer_bridge("br-access")

        assert peer is None

    def test_get_nic_speed(self, collector, mock_ssh_manager):
        """Test getting NIC speed."""
        mock_result = MagicMock()
        mock_result.stdout = "Speed: 10000Mb/s"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        speed = collector._get_nic_speed("eth0")

        assert speed == "10000Mb/s"

    def test_get_nic_speed_unknown(self, collector, mock_ssh_manager):
        """Test getting NIC speed when unknown."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "ethtool: not found"
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        speed = collector._get_nic_speed("eth0")

        assert speed == "unknown"

    def test_get_qemu_pid_by_vm_virsh(self, collector, mock_ssh_manager):
        """Test getting QEMU PID via virsh."""
        mock_result = MagicMock()
        mock_result.stdout = "12345\n"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        pid = collector.get_qemu_pid_by_vm("ae6aa164-604c-4cb0")

        assert pid == 12345

    def test_get_qemu_pid_by_vm_fallback(self, collector, mock_ssh_manager):
        """Test getting QEMU PID via ps fallback."""
        mock_result1 = MagicMock()
        mock_result1.stdout = ""
        mock_result1.stderr = ""
        mock_result1.exit_code = 1

        mock_result2 = MagicMock()
        mock_result2.stdout = "54321\n"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        mock_ssh_manager.execute.side_effect = [mock_result1, mock_result2]

        pid = collector.get_qemu_pid_by_vm("ae6aa164-604c-4cb0")

        assert pid == 54321

    def test_get_qemu_pid_by_vm_not_found(self, collector, mock_ssh_manager):
        """Test getting QEMU PID when not found."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        pid = collector.get_qemu_pid_by_vm("nonexistent")

        assert pid == 0

    def test_get_vm_nics_from_xml(self, collector, mock_ssh_manager):
        """Test getting VM NICs from XML."""
        mock_result = MagicMock()
        mock_result.stdout = """
<domain>
  <devices>
    <interface type='bridge'>
      <mac address='fa:16:3e:11:22:33'/>
      <source bridge='br-access'/>
      <target dev='vnet0'/>
      <driver name='vhost' queues='4'/>
    </interface>
    <interface type='bridge'>
      <mac address='fa:16:3e:44:55:66'/>
      <source bridge='br-storage'/>
      <target dev='vnet1'/>
    </interface>
  </devices>
</domain>
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        nics = collector.get_vm_nics_from_xml("test-vm")

        assert len(nics) == 2
        assert nics[0]["mac"] == "fa:16:3e:11:22:33"
        assert nics[0]["vnet"] == "vnet0"
        assert nics[0]["queues"] == 4
        assert nics[1]["mac"] == "fa:16:3e:44:55:66"
        assert nics[1]["vnet"] == "vnet1"
        assert nics[1]["queues"] == 1

    def test_get_vm_nics_from_xml_empty(self, collector, mock_ssh_manager):
        """Test getting VM NICs from XML when none found."""
        mock_result = MagicMock()
        mock_result.stdout = "<domain></domain>"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        nics = collector.get_vm_nics_from_xml("test-vm")

        assert len(nics) == 0

    def test_get_vm_nics_from_xml_command_fails(self, collector, mock_ssh_manager):
        """Test getting VM NICs from XML when command fails."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "VM not found"
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        nics = collector.get_vm_nics_from_xml("nonexistent")

        assert len(nics) == 0

    def test_get_tap_fd_mapping(self, collector, mock_ssh_manager):
        """Test getting TAP FD mapping."""
        mock_result1 = MagicMock()
        mock_result1.stdout = """
lrwx------ 1 qemu 34 -> /dev/net/tun
lrwx------ 1 qemu 35 -> /dev/net/tun
        """
        mock_result1.stderr = ""
        mock_result1.exit_code = 0

        mock_result2 = MagicMock()
        mock_result2.stdout = """
FD:34
iff: vnet0
FD:35
iff: vnet0
        """
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        mock_ssh_manager.execute.side_effect = [mock_result1, mock_result2]

        mapping = collector.get_tap_fd_mapping(12345)

        assert "vnet0" in mapping
        assert mapping["vnet0"] == [34, 35]

    def test_get_tap_fd_mapping_invalid_pid(self, collector, mock_ssh_manager):
        """Test getting TAP FD mapping with invalid PID."""
        mapping = collector.get_tap_fd_mapping(0)
        assert mapping == {}

        mapping = collector.get_tap_fd_mapping(-1)
        assert mapping == {}

    def test_get_tap_fd_mapping_no_taps(self, collector, mock_ssh_manager):
        """Test getting TAP FD mapping with no TAPs."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        mapping = collector.get_tap_fd_mapping(12345)

        assert mapping == {}

    def test_get_vhost_pids_by_qemu(self, collector, mock_ssh_manager):
        """Test getting vhost PIDs."""
        mock_result = MagicMock()
        mock_result.stdout = """
23456 vhost-12345
23457 vhost-12345
23458 vhost-12345
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        vhosts = collector.get_vhost_pids_by_qemu(12345)

        assert len(vhosts) == 3
        assert vhosts[0].pid == 23456
        assert vhosts[0].name == "vhost-12345"

    def test_get_vhost_pids_by_qemu_invalid_pid(self, collector, mock_ssh_manager):
        """Test getting vhost PIDs with invalid QEMU PID."""
        vhosts = collector.get_vhost_pids_by_qemu(0)
        assert vhosts == []

        vhosts = collector.get_vhost_pids_by_qemu(-1)
        assert vhosts == []

    def test_get_vhost_pids_by_qemu_none_found(self, collector, mock_ssh_manager):
        """Test getting vhost PIDs when none found."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        vhosts = collector.get_vhost_pids_by_qemu(12345)

        assert vhosts == []

    def test_get_vnet_bridge(self, collector, mock_ssh_manager):
        """Test getting vnet bridge."""
        mock_result = MagicMock()
        mock_result.stdout = "br-access\n"
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        bridge = collector.get_vnet_bridge("vnet0")

        assert bridge == "br-access"

    def test_get_vnet_bridge_not_found(self, collector, mock_ssh_manager):
        """Test getting vnet bridge when not found."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "no port named vnet99"
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        bridge = collector.get_vnet_bridge("vnet99")

        assert bridge == ""

    def test_get_bond_nic_info_ovs(self, collector, mock_ssh_manager):
        """Test getting OVS bond NIC info."""
        mock_result1 = MagicMock()
        mock_result1.stdout = """
---- bond0 ----
bond_mode: balance-slb
bond may use recirculation: no
member eth0: enabled
member eth1: enabled
        """
        mock_result1.stderr = ""
        mock_result1.exit_code = 0

        mock_result2 = MagicMock()
        mock_result2.stdout = "Speed: 10000Mb/s"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        mock_ssh_manager.execute.side_effect = [mock_result1, mock_result2, mock_result2]

        nic = collector._get_bond_nic_info("bond0", "ovs")

        assert nic is not None
        assert nic.name == "bond0"
        assert nic.is_bond is True
        assert nic.bond_type == "ovs"
        assert "eth0" in nic.bond_members
        assert "eth1" in nic.bond_members

    def test_get_bond_nic_info_linux(self, collector, mock_ssh_manager):
        """Test getting Linux bond NIC info."""
        mock_result1 = MagicMock()
        mock_result1.stdout = "eth0 eth1"
        mock_result1.stderr = ""
        mock_result1.exit_code = 0

        mock_result2 = MagicMock()
        mock_result2.stdout = "Speed: 25000Mb/s"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        mock_ssh_manager.execute.side_effect = [mock_result1, mock_result2, mock_result2]

        nic = collector._get_bond_nic_info("bond0", "linux")

        assert nic is not None
        assert nic.name == "bond0"
        assert nic.is_bond is True
        assert nic.bond_type == "linux"
        assert nic.bond_members == ["eth0", "eth1"]

    def test_get_bond_nic_info_not_bond(self, collector, mock_ssh_manager):
        """Test getting bond NIC info for non-bond."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 1
        mock_ssh_manager.execute.return_value = mock_result

        nic = collector._get_bond_nic_info("eth0", "ovs")

        assert nic is None


class TestEnvCollectionResult:
    """Tests for EnvCollectionResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[],
        )
        result = EnvCollectionResult(success=True, host="192.168.75.101", data=env)

        assert result.success is True
        assert result.host == "192.168.75.101"
        assert result.data == env
        assert result.error is None

    def test_error_result(self):
        """Test error result."""
        result = EnvCollectionResult(
            success=False,
            host="192.168.75.101",
            error="SSH connection failed",
        )

        assert result.success is False
        assert result.host == "192.168.75.101"
        assert result.data is None
        assert result.error == "SSH connection failed"


class TestBuildNetworkPath:
    """Tests for build_network_path function."""

    def test_build_vm_network_path(self):
        """Test building path from VM environment."""
        env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[
                VMNicInfo(
                    mac="fa:16:3e:11:22:33",
                    host_vnet="vnet0",
                    tap_fds=[34, 35],
                    vhost_pids=[VhostInfo(pid=23456, name="vhost-12345")],
                    ovs_bridge="br-access",
                    uplink_bridge="br-access-uplink",
                    physical_nics=[PhysicalNIC(name="bond0", speed="10000Mb/s", is_bond=True)],
                )
            ],
        )

        path = build_network_path(env)

        assert path.network_type == NetworkType.VM
        assert path.source.host == "192.168.75.101"
        assert path.source.vm_id == "ae6aa164"
        assert path.source.vnet == "vnet0"
        assert path.source.bridge == "br-access"
        assert path.source.vhost_pid == 23456
        assert path.source.physical_nic == "bond0"
        assert len(path.path_segments) == 5
        assert path.raw_env == env

    def test_build_vm_network_path_no_nics(self):
        """Test building path from VM environment with no NICs."""
        env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[],
        )

        path = build_network_path(env)

        assert path.network_type == NetworkType.VM
        assert path.source.vnet is None
        assert path.source.bridge is None

    def test_build_system_network_path(self):
        """Test building path from system environment."""
        env = SystemNetworkEnv(
            host="192.168.75.101",
            ports=[
                SystemNetworkInfo(
                    port_name="port-mgt",
                    port_type="mgt",
                    ip_address="192.168.75.101",
                    ovs_bridge="br-mgt",
                    uplink_bridge="br-mgt-uplink",
                    physical_nics=[PhysicalNIC(name="eth0", speed="10000Mb/s", is_bond=False)],
                )
            ],
        )

        path = build_network_path(env)

        assert path.network_type == NetworkType.SYSTEM
        assert path.source.host == "192.168.75.101"
        assert path.source.bridge == "br-mgt"
        assert path.source.physical_nic == "eth0"
        assert len(path.path_segments) == 4

    def test_build_system_network_path_no_ports(self):
        """Test building path from system environment with no ports."""
        env = SystemNetworkEnv(host="192.168.75.101", ports=[])

        path = build_network_path(env)

        assert path.network_type == NetworkType.SYSTEM
        assert path.source.bridge is None
        assert path.source.physical_nic is None

    def test_build_network_path_with_target(self):
        """Test building path with target environment."""
        source_env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm-1",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[
                VMNicInfo(
                    mac="fa:16:3e:11:22:33",
                    host_vnet="vnet0",
                    tap_fds=[34],
                    vhost_pids=[VhostInfo(pid=23456, name="vhost-12345")],
                    ovs_bridge="br-access",
                    uplink_bridge="br-access-uplink",
                    physical_nics=[PhysicalNIC(name="eth0", speed="10000Mb/s", is_bond=False)],
                )
            ],
        )
        target_env = VMNetworkEnv(
            vm_uuid="be7bb275",
            vm_name="test-vm-2",
            host="192.168.75.102",
            qemu_pid=54321,
            nics=[
                VMNicInfo(
                    mac="fa:16:3e:44:55:66",
                    host_vnet="vnet1",
                    tap_fds=[36],
                    vhost_pids=[VhostInfo(pid=34567, name="vhost-54321")],
                    ovs_bridge="br-access",
                    uplink_bridge="br-access-uplink",
                    physical_nics=[PhysicalNIC(name="eth1", speed="25000Mb/s", is_bond=False)],
                )
            ],
        )

        path = build_network_path(source_env, target_env)

        assert path.source.host == "192.168.75.101"
        assert path.source.vm_id == "ae6aa164"
        assert path.target is not None
        assert path.target.host == "192.168.75.102"
        assert path.target.vm_id == "be7bb275"
        assert path.target.vnet == "vnet1"
        assert path.target.vhost_pid == 34567

    def test_build_network_path_with_system_target(self):
        """Test building path with system environment as target."""
        source_env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[
                VMNicInfo(
                    mac="fa:16:3e:11:22:33",
                    host_vnet="vnet0",
                    tap_fds=[34],
                    vhost_pids=[],
                    ovs_bridge="br-access",
                    uplink_bridge="",
                    physical_nics=[],
                )
            ],
        )
        target_env = SystemNetworkEnv(
            host="192.168.75.102",
            ports=[
                SystemNetworkInfo(
                    port_name="port-mgt",
                    port_type="mgt",
                    ip_address="192.168.75.102",
                    ovs_bridge="br-mgt",
                    uplink_bridge="br-mgt-uplink",
                    physical_nics=[PhysicalNIC(name="eth0", speed="10000Mb/s", is_bond=False)],
                )
            ],
        )

        path = build_network_path(source_env, target_env)

        assert path.source.vm_id == "ae6aa164"
        assert path.target is not None
        assert path.target.host == "192.168.75.102"
        assert path.target.vm_id is None
        assert path.target.bridge == "br-mgt"


class TestPhysicalNICs:
    """Tests for physical NIC collection."""

    def test_get_physical_nics_on_bridge_cached(self, collector, mock_ssh_manager):
        """Test that NIC info is cached."""
        collector._bridge_nics_cache["br-mgt"] = [
            PhysicalNIC(name="eth0", speed="10000Mb/s", is_bond=False)
        ]

        nics = collector.get_physical_nics_on_bridge("br-mgt")

        # Should not call SSH at all
        mock_ssh_manager.execute.assert_not_called()
        assert len(nics) == 1
        assert nics[0].name == "eth0"

    def test_get_physical_nics_on_bridge_empty(self, collector, mock_ssh_manager):
        """Test getting NICs on empty bridge."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.exit_code = 0
        mock_ssh_manager.execute.return_value = mock_result

        nics = collector.get_physical_nics_on_bridge("br-empty")

        assert nics == []
        assert "br-empty" in collector._bridge_nics_cache

    def test_get_physical_nics_on_bridge_with_bond(self, collector, mock_ssh_manager):
        """Test getting NICs when bridge has a bond."""
        # First call: list-ports
        mock_result1 = MagicMock()
        mock_result1.stdout = "bond0\nvnet0"
        mock_result1.stderr = ""
        mock_result1.exit_code = 0

        # Second call: get interface type and bond mode
        mock_result2 = MagicMock()
        mock_result2.stdout = "PORT:bond0 TYPE: BOND:balance-slb\nPORT:vnet0 TYPE: BOND:"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        # Third call: bond/show
        mock_result3 = MagicMock()
        mock_result3.stdout = "member eth0: enabled\nmember eth1: enabled"
        mock_result3.stderr = ""
        mock_result3.exit_code = 0

        # Fourth/Fifth call: ethtool for speed
        mock_result4 = MagicMock()
        mock_result4.stdout = "Speed: 25000Mb/s"
        mock_result4.stderr = ""
        mock_result4.exit_code = 0

        mock_ssh_manager.execute.side_effect = [
            mock_result1, mock_result2, mock_result3, mock_result4, mock_result4
        ]

        nics = collector.get_physical_nics_on_bridge("br-uplink")

        assert len(nics) == 1
        assert nics[0].name == "bond0"
        assert nics[0].is_bond is True


class TestCollectSystemNetwork:
    """Tests for collect_system_network method."""

    def test_collect_system_network(self, collector, mock_ssh_manager):
        """Test collecting system network info."""
        # Mock OVS internal ports
        mock_result1 = MagicMock()
        mock_result1.stdout = """
        Bridge "br-mgt"
            Port "port-mgt"
                Interface "port-mgt"
        """
        mock_result1.stderr = ""
        mock_result1.exit_code = 0

        # Mock IP address
        mock_result2 = MagicMock()
        mock_result2.stdout = "inet 192.168.75.101/24"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        # Mock peer bridge not found
        mock_result3 = MagicMock()
        mock_result3.stdout = ""
        mock_result3.stderr = ""
        mock_result3.exit_code = 2

        # Mock list-ports
        mock_result4 = MagicMock()
        mock_result4.stdout = "eth0"
        mock_result4.stderr = ""
        mock_result4.exit_code = 0

        # Mock interface info
        mock_result5 = MagicMock()
        mock_result5.stdout = "PORT:eth0 TYPE: BOND:"
        mock_result5.stderr = ""
        mock_result5.exit_code = 0

        # Mock not a bond
        mock_result6 = MagicMock()
        mock_result6.stdout = ""
        mock_result6.stderr = ""
        mock_result6.exit_code = 1

        # Mock ethtool
        mock_result7 = MagicMock()
        mock_result7.stdout = "Speed: 10000Mb/s"
        mock_result7.stderr = ""
        mock_result7.exit_code = 0

        mock_ssh_manager.execute.side_effect = [
            mock_result1, mock_result2, mock_result3,
            mock_result4, mock_result5, mock_result6, mock_result7
        ]

        results = collector.collect_system_network()

        assert len(results) == 1
        assert results[0].port_name == "port-mgt"
        assert results[0].port_type == "mgt"
        assert results[0].ip_address == "192.168.75.101"

    def test_collect_system_network_with_filter(self, collector, mock_ssh_manager):
        """Test collecting system network with port type filter."""
        mock_result = MagicMock()
        mock_result.stdout = """
        Bridge "br-mgt"
            Port "port-mgt"
                Interface "port-mgt"
        Bridge "br-storage"
            Port "port-storage"
                Interface "port-storage"
        """
        mock_result.stderr = ""
        mock_result.exit_code = 0

        mock_result2 = MagicMock()
        mock_result2.stdout = "inet 192.168.100.1/24"
        mock_result2.stderr = ""
        mock_result2.exit_code = 0

        mock_result3 = MagicMock()
        mock_result3.stderr = ""
        mock_result3.exit_code = 2

        mock_result4 = MagicMock()
        mock_result4.stdout = "eth0"
        mock_result4.stderr = ""
        mock_result4.exit_code = 0

        mock_result5 = MagicMock()
        mock_result5.stdout = "PORT:eth0 TYPE: BOND:"
        mock_result5.stderr = ""
        mock_result5.exit_code = 0

        mock_result6 = MagicMock()
        mock_result6.stdout = ""
        mock_result6.exit_code = 1

        mock_result7 = MagicMock()
        mock_result7.stdout = "Speed: 10000Mb/s"
        mock_result7.exit_code = 0

        mock_ssh_manager.execute.side_effect = [
            mock_result, mock_result2, mock_result3,
            mock_result4, mock_result5, mock_result6, mock_result7
        ]

        results = collector.collect_system_network(port_type="storage")

        assert len(results) == 1
        assert results[0].port_type == "storage"
