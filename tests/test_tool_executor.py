"""Tests for ToolExecutor."""

import pytest

from netsherlock.agents.tool_executor import (
    ToolExecutor,
    ToolNotFoundError,
    get_tool_executor,
    reset_tool_executor,
)


class TestToolExecutorBasics:
    """Tests for ToolExecutor basic functionality."""

    def test_init_creates_handlers(self):
        """Executor should initialize with tool handlers."""
        executor = ToolExecutor()
        assert len(executor._sync_handlers) > 0

    def test_get_available_tools_returns_list(self):
        """get_available_tools should return sorted list."""
        executor = ToolExecutor()
        tools = executor.get_available_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0
        assert tools == sorted(tools)  # Should be sorted

    def test_is_tool_available_true_for_valid_tool(self):
        """is_tool_available returns True for known tools."""
        executor = ToolExecutor()

        assert executor.is_tool_available("grafana_query_metrics")
        assert executor.is_tool_available("collect_vm_network_env")
        assert executor.is_tool_available("execute_coordinated_measurement")
        assert executor.is_tool_available("analyze_latency_segments")

    def test_is_tool_available_false_for_unknown_tool(self):
        """is_tool_available returns False for unknown tools."""
        executor = ToolExecutor()

        assert not executor.is_tool_available("unknown_tool")
        assert not executor.is_tool_available("")
        assert not executor.is_tool_available("fake_tool_123")


class TestToolExecutorLayers:
    """Tests for tool layer classification."""

    def test_l1_tools_classified_correctly(self):
        """L1 monitoring tools should be classified as L1."""
        executor = ToolExecutor()

        l1_tools = [
            "grafana_query_metrics",
            "loki_query_logs",
            "read_node_logs",
            "read_pingmesh_logs",
            "query_host_latency",
            "query_host_loss_rate",
            "query_tcp_retransmissions",
        ]

        for tool in l1_tools:
            assert executor.get_tool_layer(tool) == "L1", f"{tool} should be L1"

    def test_l2_tools_classified_correctly(self):
        """L2 environment tools should be classified as L2."""
        executor = ToolExecutor()

        l2_tools = [
            "collect_vm_network_env",
            "collect_system_network_env",
            "build_network_path",
        ]

        for tool in l2_tools:
            assert executor.get_tool_layer(tool) == "L2", f"{tool} should be L2"

    def test_l3_tools_classified_correctly(self):
        """L3 measurement tools should be classified as L3."""
        executor = ToolExecutor()

        l3_tools = [
            "execute_coordinated_measurement",
            "measure_vm_latency_breakdown",
            "measure_packet_drop",
        ]

        for tool in l3_tools:
            assert executor.get_tool_layer(tool) == "L3", f"{tool} should be L3"

    def test_l4_tools_classified_correctly(self):
        """L4 analysis tools should be classified as L4."""
        executor = ToolExecutor()

        l4_tools = [
            "analyze_latency_segments",
            "analyze_packet_drops",
            "generate_diagnosis_report",
            "identify_root_cause",
        ]

        for tool in l4_tools:
            assert executor.get_tool_layer(tool) == "L4", f"{tool} should be L4"

    def test_unknown_tool_returns_unknown_layer(self):
        """Unknown tools should return 'unknown' layer."""
        executor = ToolExecutor()
        assert executor.get_tool_layer("nonexistent_tool") == "unknown"


class TestToolExecutorExecution:
    """Tests for tool execution."""

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_error(self):
        """Executing unknown tool should raise ToolNotFoundError."""
        executor = ToolExecutor()

        with pytest.raises(ToolNotFoundError) as exc_info:
            await executor.execute("unknown_tool", {})

        assert exc_info.value.tool_name == "unknown_tool"

    def test_unknown_tool_sync_raises_error(self):
        """Executing unknown tool sync should raise ToolNotFoundError."""
        executor = ToolExecutor()

        with pytest.raises(ToolNotFoundError) as exc_info:
            executor.execute_sync("unknown_tool", {})

        assert exc_info.value.tool_name == "unknown_tool"


class TestToolExecutorSingleton:
    """Tests for singleton behavior."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_tool_executor()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_tool_executor()

    def test_get_tool_executor_returns_same_instance(self):
        """get_tool_executor should return same instance."""
        e1 = get_tool_executor()
        e2 = get_tool_executor()
        assert e1 is e2

    def test_reset_tool_executor_clears_singleton(self):
        """reset_tool_executor should clear singleton."""
        e1 = get_tool_executor()
        reset_tool_executor()
        e2 = get_tool_executor()
        assert e1 is not e2


class TestToolExecutorCoverage:
    """Tests to verify all expected tools are available."""

    def test_all_l1_tools_available(self):
        """All L1 tools should be available."""
        executor = ToolExecutor()
        expected_l1 = [
            "grafana_query_metrics",
            "loki_query_logs",
            "read_node_logs",
            "read_pingmesh_logs",
        ]
        for tool in expected_l1:
            assert executor.is_tool_available(tool), f"L1 tool {tool} not available"

    def test_all_l2_tools_available(self):
        """All L2 tools should be available."""
        executor = ToolExecutor()
        expected_l2 = [
            "collect_vm_network_env",
            "collect_system_network_env",
        ]
        for tool in expected_l2:
            assert executor.is_tool_available(tool), f"L2 tool {tool} not available"

    def test_all_l3_tools_available(self):
        """All L3 tools should be available."""
        executor = ToolExecutor()
        expected_l3 = [
            "execute_coordinated_measurement",
            "measure_vm_latency_breakdown",
            "measure_packet_drop",
        ]
        for tool in expected_l3:
            assert executor.is_tool_available(tool), f"L3 tool {tool} not available"

    def test_all_l4_tools_available(self):
        """All L4 tools should be available."""
        executor = ToolExecutor()
        expected_l4 = [
            "analyze_latency_segments",
            "analyze_packet_drops",
            "generate_diagnosis_report",
            "identify_root_cause",
        ]
        for tool in expected_l4:
            assert executor.is_tool_available(tool), f"L4 tool {tool} not available"

    def test_tool_count_minimum(self):
        """Should have at least 15 tools available."""
        executor = ToolExecutor()
        tools = executor.get_available_tools()
        assert len(tools) >= 15, f"Expected at least 15 tools, got {len(tools)}"
