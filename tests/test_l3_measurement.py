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
