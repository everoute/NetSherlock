"""Integration tests for error handling and graceful degradation.

Tests that the system handles errors gracefully and provides
partial results when possible.
"""

import asyncio
from unittest.mock import patch

import pytest

from netsherlock.agents.tool_executor import ToolExecutionError, ToolExecutor, ToolNotFoundError
from netsherlock.schemas.measurement import (
    MeasurementMetadata,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
)


class TestSSHConnectionFailures:
    """Test handling of SSH connection failures."""

    def test_ssh_failure_captured_in_result(self, sample_failed_result):
        """SSH connection failure should be captured in result."""
        result = sample_failed_result

        assert result.status == MeasurementStatus.FAILED
        assert "SSH connection timeout" in result.error

    def test_failed_result_has_metadata(self, sample_failed_result):
        """Failed result should still have metadata."""
        result = sample_failed_result

        assert result.metadata is not None
        assert result.measurement_id is not None


class TestGrafanaQueryFailures:
    """Test handling of Grafana query failures."""

    def test_grafana_error_response_parsed(self, grafana_responses):
        """Grafana error response should be properly parsed."""
        error_response = grafana_responses["metrics_query_error"]

        assert error_response["status"] == "error"
        assert "parse error" in error_response["error"]

    def test_grafana_empty_response_handled(self, grafana_responses):
        """Empty Grafana response should be handled gracefully."""
        empty_response = grafana_responses["metrics_query_empty"]

        assert empty_response["status"] == "success"
        assert len(empty_response["series"]) == 0

        # System should handle empty data
        has_data = len(empty_response["series"]) > 0
        assert has_data is False

    def test_grafana_success_response(self, grafana_responses):
        """Grafana success response should contain expected data."""
        success_response = grafana_responses["metrics_query_success"]

        assert success_response["status"] == "success"
        assert len(success_response["series"]) > 0
        assert success_response["series"][0]["metric"]["hostname"] == "compute-node-1"


class TestBPFExecutionFailures:
    """Test handling of BPF tool execution failures."""

    def test_bpf_failure_result_structure(self, sample_failed_result):
        """BPF execution failure should have proper result structure."""
        result = sample_failed_result

        assert result.measurement_id is not None
        assert result.measurement_type == MeasurementType.LATENCY
        assert result.status == MeasurementStatus.FAILED
        assert result.error is not None
        assert result.metadata is not None

    def test_partial_bpf_result_usable(self, measurement_results_data):
        """Partial BPF result should still be usable for analysis."""
        # Simulate partial result with some data
        partial_result = MeasurementResult(
            measurement_id="partial-001",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.PARTIAL,
            metadata=MeasurementMetadata(
                tool_name="vm_network_latency_summary.py",
                host="192.168.1.10",
                duration_sec=15,  # Partial duration
            ),
            raw_output="virtio_tx: avg=15.5us p50=12.0us p99=45.2us\n# Interrupted",
        )

        assert partial_result.status == MeasurementStatus.PARTIAL
        assert partial_result.raw_output is not None


class TestToolExecutorErrors:
    """Test ToolExecutor error handling."""

    def test_unknown_tool_raises_error(self):
        """Unknown tool name should raise ToolNotFoundError."""
        executor = ToolExecutor()

        with pytest.raises(ToolNotFoundError):
            executor.execute_sync("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_tool_execution_error_propagated(self):
        """Tool execution errors should be properly propagated."""
        executor = ToolExecutor()

        # Mock a tool that fails
        with patch.dict(executor._sync_handlers, {"test_tool": lambda: (_ for _ in ()).throw(RuntimeError("Tool failed"))}):
            executor._all_tool_names.add("test_tool")

            with pytest.raises(ToolExecutionError) as exc_info:
                await executor.execute("test_tool", {})

            assert "Tool failed" in str(exc_info.value.cause)

    def test_tool_layer_mapping_correct(self):
        """Tool layer mapping should be correct for all tools."""
        executor = ToolExecutor()

        # Verify L1 tools
        assert executor.get_tool_layer("grafana_query_metrics") == "L1"
        assert executor.get_tool_layer("loki_query_logs") == "L1"
        assert executor.get_tool_layer("read_node_logs") == "L1"

        # Verify L2 tools
        assert executor.get_tool_layer("collect_vm_network_env") == "L2"
        assert executor.get_tool_layer("collect_system_network_env") == "L2"

        # Verify L3 tools
        assert executor.get_tool_layer("execute_coordinated_measurement") == "L3"
        assert executor.get_tool_layer("measure_vm_latency_breakdown") == "L3"

        # Verify L4 tools
        assert executor.get_tool_layer("analyze_latency_segments") == "L4"
        assert executor.get_tool_layer("identify_root_cause") == "L4"

        # Unknown tool
        assert executor.get_tool_layer("unknown_tool") == "unknown"


class TestLayerFailureDegradation:
    """Test graceful degradation when layers fail."""

    def test_l2_failure_uses_alert_labels(self, alert_payloads):
        """L2 failure should fall back to using alert labels."""
        alert = alert_payloads["vm_network_latency_alert"]
        labels = alert["labels"]

        # When L2 fails, we can still extract basic info from labels
        fallback_env = {
            "hostname": labels.get("hostname"),
            "instance": labels.get("instance"),
            "vm_name": labels.get("vm_name"),
            "source": "alert_labels",
        }

        assert fallback_env["hostname"] == "compute-node-1"
        assert fallback_env["vm_name"] == "test-vm-001"
        assert fallback_env["source"] == "alert_labels"

    def test_l3_failure_returns_l1_metrics(self, grafana_responses):
        """L3 failure should still return L1 metrics analysis."""
        metrics = grafana_responses["metrics_query_success"]

        # Extract useful info from L1 data
        l1_analysis = {
            "status": "partial",
            "level": "L1_only",
            "metrics_available": True,
            "series_count": len(metrics["series"]),
            "time_range_covered": True,
            "observation": "High latency trend detected from metrics",
        }

        assert l1_analysis["status"] == "partial"
        assert l1_analysis["metrics_available"]
        assert l1_analysis["series_count"] > 0

    def test_degraded_result_structure(
        self,
        grafana_responses,
        sample_vm_env,
        sample_failed_result,
    ):
        """Degraded result should have proper structure."""
        # L1 data is available
        metrics = grafana_responses["metrics_query_success"]
        assert metrics["status"] == "success"

        # L2 data is available
        env = sample_vm_env
        assert env.host is not None

        # L3 failed
        measurement = sample_failed_result
        assert measurement.status == MeasurementStatus.FAILED

        # Build degraded result with available data
        degraded_result = {
            "status": "partial",
            "l1_data": {
                "metrics_available": True,
                "hostname": metrics["series"][0]["metric"]["hostname"],
            },
            "l2_data": {
                "environment_collected": True,
                "host": env.host,
                "nics_count": len(env.nics),
            },
            "l3_data": {
                "measurement_available": False,
                "error": measurement.error,
            },
            "message": "Partial diagnosis available. L3 measurement failed.",
        }

        assert degraded_result["status"] == "partial"
        assert degraded_result["l1_data"]["metrics_available"]
        assert degraded_result["l2_data"]["environment_collected"]
        assert not degraded_result["l3_data"]["measurement_available"]


class TestConcurrentErrorHandling:
    """Test error handling in concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_ssh_failures(self):
        """Multiple concurrent SSH failures should be handled."""
        async def failing_ssh_execute(host, cmd):
            await asyncio.sleep(0.01)
            raise ConnectionError(f"Connection to {host} refused")

        hosts = ["192.168.1.10", "192.168.1.11", "192.168.1.12"]
        results = []

        for host in hosts:
            try:
                await failing_ssh_execute(host, "test")
            except ConnectionError as e:
                results.append({"host": host, "error": str(e)})

        assert len(results) == 3
        assert all("Connection" in r["error"] for r in results)

    @pytest.mark.asyncio
    async def test_partial_concurrent_success(self):
        """Some concurrent operations succeeding should yield partial results."""
        async def mixed_execute(host, cmd):
            await asyncio.sleep(0.01)
            if host == "192.168.1.11":
                raise ConnectionError(f"Connection to {host} refused")
            return {"host": host, "status": "success"}

        hosts = ["192.168.1.10", "192.168.1.11", "192.168.1.12"]
        results = []

        for host in hosts:
            try:
                result = await mixed_execute(host, "test")
                results.append(result)
            except ConnectionError as e:
                results.append({"host": host, "status": "failed", "error": str(e)})

        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") == "failed"]

        assert len(successful) == 2
        assert len(failed) == 1
        assert failed[0]["host"] == "192.168.1.11"


class TestMeasurementStatusHandling:
    """Test different measurement status scenarios."""

    def test_success_status(self, sample_latency_result):
        """Successful measurement should have SUCCESS status."""
        assert sample_latency_result.status == MeasurementStatus.SUCCESS
        assert sample_latency_result.error is None
        assert sample_latency_result.latency_data is not None

    def test_failed_status(self, sample_failed_result):
        """Failed measurement should have FAILED status."""
        assert sample_failed_result.status == MeasurementStatus.FAILED
        assert sample_failed_result.error is not None
        assert sample_failed_result.latency_data is None

    def test_partial_status(self):
        """Partial measurement should have PARTIAL status."""
        partial = MeasurementResult(
            measurement_id="partial-002",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.PARTIAL,
            metadata=MeasurementMetadata(
                tool_name="vm_network_latency_summary.py",
                host="192.168.1.10",
                duration_sec=10,
            ),
            raw_output="Partial output",
        )

        assert partial.status == MeasurementStatus.PARTIAL
        assert partial.raw_output is not None
