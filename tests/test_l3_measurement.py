"""Tests for L3 measurement tools and receiver-first timing.

These tests verify the receiver-first timing constraint for coordinated
measurements, which is a critical requirement for accurate latency measurement.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from netsherlock.core.bpf_executor import (
    BPFExecutionResult,
    BPFExecutor,
    CoordinatedMeasurement,
)
from netsherlock.schemas.measurement import (
    CoordinatedMeasurementResult,
    LatencyBreakdown,
    LatencySegment,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
    PacketDropResult,
)
from netsherlock.tools.l3_measurement import (
    _parse_latency_output,
    _parse_drop_output,
    _build_command,
)


class TestReceiverFirstTiming:
    """Tests for receiver-first timing constraint."""

    def test_coordinated_measurement_has_receiver_delay(self):
        """CoordinatedMeasurement should have receiver_startup_delay."""
        ssh_mock = MagicMock()
        coord = CoordinatedMeasurement(
            ssh_mock,
            receiver_ready_timeout=10,
            receiver_startup_delay=2.0,
        )

        assert coord.receiver_startup_delay == 2.0
        assert coord.receiver_ready_timeout == 10

    def test_default_receiver_delay_is_one_second(self):
        """Default receiver startup delay should be 1 second."""
        ssh_mock = MagicMock()
        coord = CoordinatedMeasurement(ssh_mock)

        assert coord.receiver_startup_delay == 1.0

    def test_receiver_starts_before_sender_in_thread_order(self):
        """Verify the execution order: receiver thread, then sender."""
        # This test verifies the structure of CoordinatedMeasurement.execute()
        # The receiver is started in a thread before the sender runs

        # Check that the code structure enforces receiver-first
        import inspect
        from netsherlock.core.bpf_executor import CoordinatedMeasurement

        source = inspect.getsource(CoordinatedMeasurement.execute)

        # Verify receiver thread starts before time.sleep (receiver ready wait)
        receiver_start_pos = source.find("receiver_thread.start()")
        time_sleep_pos = source.find("time.sleep(self.receiver_startup_delay)")
        sender_start_pos = source.find("sender_result = sender_executor.execute")

        assert receiver_start_pos < time_sleep_pos < sender_start_pos, (
            "Receiver must start before delay, and sender must start after delay"
        )


class TestLatencyParsing:
    """Tests for latency output parsing."""

    def test_parse_latency_output_extracts_segments(self):
        """Should parse segment statistics from output."""
        output = """
        virtio_tx: avg=50.5us p50=45.0us p99=120.0us
        vhost_net: avg=30.2us p50=28.0us p99=80.0us
        """

        result = _parse_latency_output(output)

        assert isinstance(result, LatencyBreakdown)
        assert len(result.segments) == 2
        assert result.segments[0].name == "virtio_tx"
        assert result.segments[0].avg_us == 50.5
        assert result.segments[0].p99_us == 120.0

    def test_parse_latency_output_calculates_totals(self):
        """Should calculate total latency from segments."""
        output = """
        segment1: avg=100.0us p50=90.0us p99=200.0us
        segment2: avg=50.0us p50=45.0us p99=100.0us
        """

        result = _parse_latency_output(output)

        assert result.total_avg_us == 150.0  # 100 + 50
        assert result.total_p99_us == 300.0  # 200 + 100

    def test_parse_latency_output_empty_input(self):
        """Should return empty breakdown for empty input."""
        result = _parse_latency_output("")

        assert len(result.segments) == 0
        assert result.total_avg_us == 0
        assert result.total_p99_us == 0


class TestDropParsing:
    """Tests for packet drop output parsing."""

    def test_parse_drop_output_extracts_locations(self):
        """Should parse drop locations from output."""
        output = """
        nf_hook_slow: 15 drops
        tcp_v4_rcv: 3 drops
        """

        result = _parse_drop_output(output)

        assert isinstance(result, PacketDropResult)
        assert len(result.drop_points) == 2
        assert result.total_drops == 18  # 15 + 3

    def test_parse_drop_output_empty_input(self):
        """Should return empty result for no drops."""
        result = _parse_drop_output("")

        assert result.total_drops == 0
        assert len(result.drop_points) == 0


class TestBuildCommand:
    """Tests for command building."""

    def test_build_command_python_script(self):
        """Should prefix Python scripts with interpreter."""
        cmd = _build_command("my_script.py", {"arg1": "value1"})

        assert "python" in cmd
        assert "my_script.py" in cmd
        assert "--arg1 value1" in cmd

    def test_build_command_with_args(self):
        """Should include all arguments."""
        cmd = _build_command("script.py", {
            "interface": "eth0",
            "duration": 30,
        })

        assert "--interface eth0" in cmd
        assert "--duration 30" in cmd

    def test_build_command_skips_none_args(self):
        """Should skip None argument values."""
        cmd = _build_command("script.py", {
            "arg1": "value1",
            "arg2": None,
        })

        assert "--arg1 value1" in cmd
        assert "arg2" not in cmd


class TestBPFExecutor:
    """Tests for BPFExecutor."""

    def test_executor_init(self):
        """Should initialize with defaults."""
        ssh_mock = MagicMock()
        executor = BPFExecutor(ssh_mock, "192.168.1.10")

        assert executor.host == "192.168.1.10"
        assert executor.ssh == ssh_mock

    def test_executor_check_tool_exists(self):
        """Should check tool existence via SSH."""
        ssh_mock = MagicMock()
        ssh_mock.execute.return_value = MagicMock(success=True)

        executor = BPFExecutor(ssh_mock, "192.168.1.10")
        result = executor.check_tool_exists("my_tool.py")

        assert result is True
        ssh_mock.execute.assert_called_once()


class TestBPFExecutionResult:
    """Tests for BPFExecutionResult."""

    def test_success_result(self):
        """Should represent successful execution."""
        result = BPFExecutionResult(
            success=True,
            stdout="output data",
            stderr="",
            exit_code=0,
            duration_actual=30.5,
        )

        assert result.success
        assert result.stdout == "output data"
        assert result.exit_code == 0
        assert result.duration_actual == 30.5

    def test_failed_result(self):
        """Should represent failed execution."""
        result = BPFExecutionResult(
            success=False,
            stdout="",
            stderr="error message",
            exit_code=1,
            error="Connection failed",
        )

        assert not result.success
        assert result.error == "Connection failed"
        assert result.exit_code == 1


class TestMeasurementResult:
    """Tests for MeasurementResult schema."""

    @pytest.fixture
    def metadata(self):
        """Create test metadata."""
        from netsherlock.schemas.measurement import MeasurementMetadata
        return MeasurementMetadata(
            tool_name="test_tool.py",
            host="192.168.1.10",
            duration_sec=30.0,
        )

    def test_latency_measurement_result(self, metadata):
        """Should create valid latency measurement result."""
        result = MeasurementResult(
            measurement_id="test-123",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.SUCCESS,
            latency_data=LatencyBreakdown(
                segments=[
                    LatencySegment(name="seg1", avg_us=50.0, p99_us=100.0)
                ],
                total_avg_us=50.0,
                total_p99_us=100.0,
            ),
            metadata=metadata,
        )

        assert result.measurement_type == MeasurementType.LATENCY
        assert result.status == MeasurementStatus.SUCCESS
        assert result.latency_data is not None
        assert len(result.latency_data.segments) == 1

    def test_failed_measurement_result(self, metadata):
        """Should create valid failed result."""
        result = MeasurementResult(
            measurement_id="test-456",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.FAILED,
            error="SSH connection failed",
            metadata=metadata,
        )

        assert result.status == MeasurementStatus.FAILED
        assert result.error == "SSH connection failed"


class TestCoordinatedMeasurementResult:
    """Tests for CoordinatedMeasurementResult."""

    @pytest.fixture
    def metadata(self):
        """Create test metadata."""
        from netsherlock.schemas.measurement import MeasurementMetadata
        return MeasurementMetadata(
            tool_name="test_tool.py",
            host="192.168.1.10",
            duration_sec=30.0,
        )

    def test_coordinated_result_has_both_sides(self, metadata):
        """Should contain both receiver and sender results."""
        receiver = MeasurementResult(
            measurement_id="rx-123",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.SUCCESS,
            metadata=metadata,
        )
        sender = MeasurementResult(
            measurement_id="tx-123",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.SUCCESS,
            metadata=metadata,
        )

        coordinated = CoordinatedMeasurementResult(
            measurement_id="coord-123",
            receiver_result=receiver,
            sender_result=sender,
        )

        assert coordinated.receiver_result.measurement_id == "rx-123"
        assert coordinated.sender_result.measurement_id == "tx-123"


class TestExecuteCoordinatedMeasurement:
    """Tests for execute_coordinated_measurement function."""

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    @patch("netsherlock.tools.l3_measurement.CoordinatedMeasurement")
    def test_successful_measurement(
        self, mock_coord_class, mock_ssh_class, mock_settings
    ):
        """Test successful coordinated measurement."""
        from netsherlock.tools.l3_measurement import execute_coordinated_measurement

        # Setup mocks
        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.measurement.receiver_ready_timeout = 5
        mock_settings.return_value.measurement.receiver_startup_delay = 1
        mock_settings.return_value.bpf_tools.local_tools_path = "/tools"
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh = MagicMock()
        mock_ssh_class.return_value.__enter__ = MagicMock(return_value=mock_ssh)
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        # Mock execution result
        receiver_result = MagicMock()
        receiver_result.success = True
        receiver_result.stdout = "virtio_rx: avg=100.0us p50=80.0us p99=500.0us"
        receiver_result.error = None
        receiver_result.duration_actual = 30

        sender_result = MagicMock()
        sender_result.success = True
        sender_result.stdout = "virtio_tx: avg=150.0us p50=120.0us p99=600.0us"
        sender_result.error = None
        sender_result.duration_actual = 30

        mock_coord = MagicMock()
        mock_coord.execute.return_value = (receiver_result, sender_result)
        mock_coord_class.return_value = mock_coord

        result = execute_coordinated_measurement(
            receiver_host="192.168.75.102",
            sender_host="192.168.75.101",
            receiver_tool="receiver.py",
            sender_tool="sender.py",
            duration=30,
        )

        assert result.receiver_result.status == MeasurementStatus.SUCCESS
        assert result.sender_result.status == MeasurementStatus.SUCCESS

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    def test_measurement_exception(self, mock_ssh_class, mock_settings):
        """Test measurement handles exception."""
        from netsherlock.tools.l3_measurement import execute_coordinated_measurement

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.measurement.receiver_ready_timeout = 5
        mock_settings.return_value.measurement.receiver_startup_delay = 1
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh_class.return_value.__enter__ = MagicMock(
            side_effect=Exception("Connection failed")
        )
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        result = execute_coordinated_measurement(
            receiver_host="192.168.75.102",
            sender_host="192.168.75.101",
            receiver_tool="receiver.py",
            sender_tool="sender.py",
        )

        assert result.receiver_result.status == MeasurementStatus.FAILED
        assert result.sender_result.status == MeasurementStatus.FAILED
        assert "Connection failed" in result.receiver_result.error


class TestMeasureVmLatencyBreakdown:
    """Tests for measure_vm_latency_breakdown function."""

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    @patch("netsherlock.tools.l3_measurement.BPFExecutor")
    def test_successful_measurement_with_env(
        self, mock_executor_class, mock_ssh_class, mock_settings
    ):
        """Test successful measurement with pre-collected environment."""
        from netsherlock.tools.l3_measurement import measure_vm_latency_breakdown
        from netsherlock.schemas.environment import VMNetworkEnv, VMNicInfo, VhostInfo

        # Setup mocks
        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh = MagicMock()
        mock_ssh_class.return_value.__enter__ = MagicMock(return_value=mock_ssh)
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = "virtio_tx: avg=100.0us p50=80.0us p99=500.0us"
        mock_result.error = None
        mock_result.duration_actual = 30

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[
                VMNicInfo(
                    mac="fa:16:3e:11:22:33",
                    host_vnet="vnet0",
                    tap_fds=[34],
                    vhost_pids=[VhostInfo(pid=23456, name="vhost-12345")],
                    ovs_bridge="br-access",
                    uplink_bridge="",
                    physical_nics=[],
                )
            ],
        )

        result = measure_vm_latency_breakdown(
            vm_id="ae6aa164",
            host="192.168.75.101",
            env=env,
            duration=30,
        )

        assert result.status == MeasurementStatus.SUCCESS
        assert result.latency_data is not None

    @patch("netsherlock.tools.l3_measurement.get_settings")
    def test_measurement_no_nics(self, mock_settings):
        """Test measurement fails with no NICs."""
        from netsherlock.tools.l3_measurement import measure_vm_latency_breakdown
        from netsherlock.schemas.environment import VMNetworkEnv

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"

        env = VMNetworkEnv(
            vm_uuid="ae6aa164",
            vm_name="test-vm",
            host="192.168.75.101",
            qemu_pid=12345,
            nics=[],
        )

        result = measure_vm_latency_breakdown(
            vm_id="ae6aa164",
            host="192.168.75.101",
            env=env,
            duration=30,
        )

        assert result.status == MeasurementStatus.FAILED
        assert "No NICs found" in result.error

    @patch("netsherlock.tools.l2_environment.collect_vm_network_env")
    @patch("netsherlock.tools.l3_measurement.get_settings")
    def test_measurement_env_collection_fails(self, mock_settings, mock_collect):
        """Test measurement handles env collection failure."""
        from netsherlock.tools.l3_measurement import measure_vm_latency_breakdown
        from netsherlock.tools.l2_environment import EnvCollectionResult

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"

        mock_collect.return_value = EnvCollectionResult(
            success=False,
            host="192.168.75.101",
            error="SSH connection failed",
        )

        result = measure_vm_latency_breakdown(
            vm_id="ae6aa164",
            host="192.168.75.101",
            env=None,
            duration=30,
        )

        assert result.status == MeasurementStatus.FAILED
        assert "Failed to collect VM environment" in result.error

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    def test_measurement_exception(self, mock_ssh_class, mock_settings):
        """Test measurement handles exception."""
        from netsherlock.tools.l3_measurement import measure_vm_latency_breakdown
        from netsherlock.schemas.environment import VMNetworkEnv, VMNicInfo

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh_class.return_value.__enter__ = MagicMock(
            side_effect=Exception("Connection failed")
        )
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        env = VMNetworkEnv(
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

        result = measure_vm_latency_breakdown(
            vm_id="ae6aa164",
            host="192.168.75.101",
            env=env,
            duration=30,
        )

        assert result.status == MeasurementStatus.FAILED
        assert "Connection failed" in result.error


class TestMeasurePacketDrop:
    """Tests for measure_packet_drop function."""

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    @patch("netsherlock.tools.l3_measurement.BPFExecutor")
    def test_successful_measurement(
        self, mock_executor_class, mock_ssh_class, mock_settings
    ):
        """Test successful packet drop measurement."""
        from netsherlock.tools.l3_measurement import measure_packet_drop

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh = MagicMock()
        mock_ssh_class.return_value.__enter__ = MagicMock(return_value=mock_ssh)
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = "kfree_skb: 50 drops"
        mock_result.error = None
        mock_result.duration_actual = 30

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        result = measure_packet_drop(
            host="192.168.75.101",
            interface="eth0",
            duration=30,
        )

        assert result.status == MeasurementStatus.SUCCESS
        assert result.drop_data is not None
        assert result.drop_data.total_drops == 50

    @patch("netsherlock.tools.l3_measurement.get_settings")
    @patch("netsherlock.tools.l3_measurement.SSHManager")
    def test_measurement_exception(self, mock_ssh_class, mock_settings):
        """Test packet drop measurement handles exception."""
        from netsherlock.tools.l3_measurement import measure_packet_drop

        mock_settings.return_value.ssh = MagicMock()
        mock_settings.return_value.bpf_tools.remote_tools_path = "/remote/tools"
        mock_settings.return_value.bpf_tools.remote_python = "python3"

        mock_ssh_class.return_value.__enter__ = MagicMock(
            side_effect=Exception("SSH error")
        )
        mock_ssh_class.return_value.__exit__ = MagicMock(return_value=None)

        result = measure_packet_drop(
            host="192.168.75.101",
            duration=30,
        )

        assert result.status == MeasurementStatus.FAILED
        assert "SSH error" in result.error


class TestParseMeasurementResult:
    """Tests for _parse_measurement_result function."""

    def test_parse_failed_result(self):
        """Test parsing failed execution result."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = False
        raw_result.error = "Execution timeout"
        raw_result.stdout = ""
        raw_result.duration_actual = 0

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.LATENCY,
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.FAILED
        assert result.error == "Execution timeout"
        assert result.metadata.host == "192.168.75.101"

    def test_parse_latency_success(self):
        """Test parsing successful latency result."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = True
        raw_result.error = None
        raw_result.stdout = "virtio_tx: avg=100.0us p50=80.0us p99=500.0us"
        raw_result.duration_actual = 30

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.LATENCY,
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.SUCCESS
        assert result.latency_data is not None
        assert len(result.latency_data.segments) == 1

    def test_parse_latency_partial(self):
        """Test parsing latency result with no segments."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = True
        raw_result.error = None
        raw_result.stdout = "No data collected"
        raw_result.duration_actual = 30

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.LATENCY,
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.PARTIAL
        assert result.latency_data.segments == []

    def test_parse_drop_success(self):
        """Test parsing successful packet drop result."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = True
        raw_result.error = None
        raw_result.stdout = "kfree_skb: 50 drops"
        raw_result.duration_actual = 30

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.PACKET_DROP,
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.SUCCESS
        assert result.drop_data is not None
        assert result.drop_data.total_drops == 50

    def test_parse_unknown_type(self):
        """Test parsing with throughput measurement type (not latency/drop)."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = True
        raw_result.error = None
        raw_result.stdout = "some output"
        raw_result.duration_actual = 30

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.THROUGHPUT,  # Use THROUGHPUT instead
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.PARTIAL
        assert result.raw_output == "some output"

    def test_parse_failed_no_error(self):
        """Test parsing failed result without error message."""
        from netsherlock.tools.l3_measurement import _parse_measurement_result

        raw_result = MagicMock()
        raw_result.success = False
        raw_result.error = None
        raw_result.stdout = ""
        raw_result.duration_actual = 0

        result = _parse_measurement_result(
            raw_result=raw_result,
            measurement_type=MeasurementType.LATENCY,
            host="192.168.75.101",
            tool_name="test_tool.py",
        )

        assert result.status == MeasurementStatus.FAILED
        assert result.error == "Execution failed"


class TestToolPaths:
    """Tests for tool path constants."""

    def test_latency_tools_defined(self):
        """Test latency tools are defined."""
        from netsherlock.tools.l3_measurement import LATENCY_TOOLS

        assert "vm_network" in LATENCY_TOOLS
        assert "system_network" in LATENCY_TOOLS
        assert "vhost_tun" in LATENCY_TOOLS

    def test_drop_tools_defined(self):
        """Test drop tools are defined."""
        from netsherlock.tools.l3_measurement import DROP_TOOLS

        assert "kernel_drop" in DROP_TOOLS
        assert "icmp_drop" in DROP_TOOLS
