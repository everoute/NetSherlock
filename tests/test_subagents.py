"""Tests for L2, L3, L4 Subagents."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the claude_code_sdk module before importing subagents
mock_sdk = MagicMock()
sys.modules["claude_code_sdk"] = mock_sdk

from netsherlock.agents.base import (
    LatencyHistogram,
    LatencySegment,
    MeasurementResult,
    NetworkEnvironment,
    NodeEnvironment,
    ProblemType,
)
from netsherlock.agents.subagents import (
    L2EnvironmentSubagent,
    L3MeasurementSubagent,
    L4AnalysisSubagent,
    create_subagent,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.llm.model = "claude-sonnet-4-20250514"
    settings.llm.compact_prompts = False
    return settings


class TestL2EnvironmentSubagentInit:
    """Tests for L2 subagent initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Initialize with provided settings."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        assert subagent.model == "claude-sonnet-4-20250514"

    def test_init_with_model_override(self, mock_settings: MagicMock) -> None:
        """Model override takes precedence over settings."""
        subagent = L2EnvironmentSubagent(
            settings=mock_settings,
            model="claude-opus-4-20250514",
        )

        assert subagent.model == "claude-opus-4-20250514"

    def test_init_with_compact_prompt(self, mock_settings: MagicMock) -> None:
        """compact_prompt affects system prompt."""
        subagent_normal = L2EnvironmentSubagent(
            settings=mock_settings,
            compact_prompt=False,
        )
        subagent_compact = L2EnvironmentSubagent(
            settings=mock_settings,
            compact_prompt=True,
        )

        # Prompts should be different lengths
        assert subagent_normal.system_prompt != subagent_compact.system_prompt

    @patch("netsherlock.config.settings.get_settings")
    def test_init_without_settings(
        self, mock_get_settings: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Uses default settings when none provided."""
        mock_get_settings.return_value = mock_settings

        L2EnvironmentSubagent()

        mock_get_settings.assert_called()

    def test_init_creates_tools(self, mock_settings: MagicMock) -> None:
        """Tools are created during initialization."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        assert subagent._tools is not None
        assert len(subagent._tools) > 0


class TestL2EnvironmentSubagentTools:
    """Tests for L2 subagent tool definitions."""

    def test_l2_tools_contain_collect_vm_network_env(
        self, mock_settings: MagicMock
    ) -> None:
        """L2 tools include collect_vm_network_env."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "collect_vm_network_env" in tool_names

    def test_l2_tools_contain_collect_system_network_env(
        self, mock_settings: MagicMock
    ) -> None:
        """L2 tools include collect_system_network_env."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "collect_system_network_env" in tool_names

    def test_l2_tools_contain_resolve_network_path(
        self, mock_settings: MagicMock
    ) -> None:
        """L2 tools include resolve_network_path."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "resolve_network_path" in tool_names

    def test_l2_tool_schema_structure(self, mock_settings: MagicMock) -> None:
        """Tool definitions have correct schema structure."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        for tool in subagent._tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_collect_vm_network_env_schema(self, mock_settings: MagicMock) -> None:
        """collect_vm_network_env has correct required parameters."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        vm_tool = next(t for t in subagent._tools if t["name"] == "collect_vm_network_env")

        assert "node_ip" in vm_tool["input_schema"]["required"]
        assert "vm_identifier" in vm_tool["input_schema"]["required"]


class TestL2EnvironmentSubagentParseEnvironment:
    """Tests for L2 environment parsing."""

    def test_parse_environment_not_implemented(self, mock_settings: MagicMock) -> None:
        """_parse_environment raises NotImplementedError."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        with pytest.raises(NotImplementedError):
            subagent._parse_environment(None)


class TestL3MeasurementSubagentInit:
    """Tests for L3 subagent initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Initialize with provided settings."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        assert subagent.model == "claude-sonnet-4-20250514"

    def test_init_with_model_override(self, mock_settings: MagicMock) -> None:
        """Model override takes precedence over settings."""
        subagent = L3MeasurementSubagent(
            settings=mock_settings,
            model="claude-opus-4-20250514",
        )

        assert subagent.model == "claude-opus-4-20250514"

    def test_init_creates_tools(self, mock_settings: MagicMock) -> None:
        """Tools are created during initialization."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        assert subagent._tools is not None
        assert len(subagent._tools) > 0


class TestL3MeasurementSubagentTools:
    """Tests for L3 subagent tool definitions."""

    def test_l3_tools_contain_execute_coordinated_measurement(
        self, mock_settings: MagicMock
    ) -> None:
        """L3 tools include execute_coordinated_measurement."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "execute_coordinated_measurement" in tool_names

    def test_l3_tools_contain_measure_vm_latency_breakdown(
        self, mock_settings: MagicMock
    ) -> None:
        """L3 tools include measure_vm_latency_breakdown."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "measure_vm_latency_breakdown" in tool_names

    def test_l3_tools_contain_measure_system_latency_breakdown(
        self, mock_settings: MagicMock
    ) -> None:
        """L3 tools include measure_system_latency_breakdown."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "measure_system_latency_breakdown" in tool_names

    def test_l3_tools_contain_detect_packet_drops(
        self, mock_settings: MagicMock
    ) -> None:
        """L3 tools include detect_packet_drops."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "detect_packet_drops" in tool_names

    def test_coordinated_measurement_schema(self, mock_settings: MagicMock) -> None:
        """execute_coordinated_measurement has correct schema."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        coord_tool = next(
            t for t in subagent._tools if t["name"] == "execute_coordinated_measurement"
        )

        required = coord_tool["input_schema"]["required"]
        assert "measurement_type" in required
        assert "receiver" in required
        assert "sender" in required


class TestL3MeasurementSubagentParseMeasurement:
    """Tests for L3 measurement parsing."""

    def test_parse_measurement_not_implemented(self, mock_settings: MagicMock) -> None:
        """_parse_measurement raises NotImplementedError."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        with pytest.raises(NotImplementedError):
            subagent._parse_measurement(None)


class TestL4AnalysisSubagentInit:
    """Tests for L4 subagent initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Initialize with provided settings."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        assert subagent.model == "claude-sonnet-4-20250514"

    def test_init_with_model_override(self, mock_settings: MagicMock) -> None:
        """Model override takes precedence over settings."""
        subagent = L4AnalysisSubagent(
            settings=mock_settings,
            model="claude-opus-4-20250514",
        )

        assert subagent.model == "claude-opus-4-20250514"

    def test_init_creates_tools(self, mock_settings: MagicMock) -> None:
        """Tools are created during initialization."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        assert subagent._tools is not None
        assert len(subagent._tools) > 0


class TestL4AnalysisSubagentTools:
    """Tests for L4 subagent tool definitions."""

    def test_l4_tools_contain_analyze_latency_segments(
        self, mock_settings: MagicMock
    ) -> None:
        """L4 tools include analyze_latency_segments."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "analyze_latency_segments" in tool_names

    def test_l4_tools_contain_identify_root_cause(
        self, mock_settings: MagicMock
    ) -> None:
        """L4 tools include identify_root_cause."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "identify_root_cause" in tool_names

    def test_l4_tools_contain_generate_diagnosis_report(
        self, mock_settings: MagicMock
    ) -> None:
        """L4 tools include generate_diagnosis_report."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        tool_names = [t["name"] for t in subagent._tools]

        assert "generate_diagnosis_report" in tool_names

    def test_analyze_latency_segments_schema(self, mock_settings: MagicMock) -> None:
        """analyze_latency_segments has correct schema."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        analyze_tool = next(
            t for t in subagent._tools if t["name"] == "analyze_latency_segments"
        )

        assert "segments" in analyze_tool["input_schema"]["required"]


class TestL4AnalysisSubagentFormatSegments:
    """Tests for L4 segment formatting."""

    def test_format_segments_empty(self, mock_settings: MagicMock) -> None:
        """Format empty segments list."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        result = subagent._format_segments([])

        assert result == ""

    def test_format_segments_single(self, mock_settings: MagicMock) -> None:
        """Format single segment."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        histogram = LatencyHistogram(
            p50_us=100.0,
            p95_us=200.0,
            p99_us=300.0,
            max_us=500.0,
            samples=1000,
        )
        segments = [
            LatencySegment(
                name="segment_a",
                layer="vm_internal",
                histogram=histogram,
            )
        ]

        result = subagent._format_segments(segments)

        assert "segment_a" in result
        assert "vm_internal" in result

    def test_format_segments_multiple(self, mock_settings: MagicMock) -> None:
        """Format multiple segments."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        histogram = LatencyHistogram(
            p50_us=100.0,
            p95_us=200.0,
            p99_us=300.0,
            max_us=500.0,
        )
        segments = [
            LatencySegment(name="segment_a", layer="vm_internal", histogram=histogram),
            LatencySegment(name="segment_b", layer="vhost_processing", histogram=histogram),
            LatencySegment(name="segment_c", layer="host_internal", histogram=histogram),
        ]

        result = subagent._format_segments(segments)

        assert "segment_a" in result
        assert "segment_b" in result
        assert "segment_c" in result


class TestL4AnalysisSubagentParseDiagnosis:
    """Tests for L4 diagnosis parsing."""

    def test_parse_diagnosis_not_implemented(self, mock_settings: MagicMock) -> None:
        """_parse_diagnosis raises NotImplementedError."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        with pytest.raises(NotImplementedError):
            subagent._parse_diagnosis(None)


class TestCreateSubagent:
    """Tests for create_subagent factory function."""

    def test_create_l2_subagent(self) -> None:
        """create_subagent creates L2 subagent."""
        subagent = create_subagent("l2")

        assert isinstance(subagent, L2EnvironmentSubagent)

    def test_create_l3_subagent(self) -> None:
        """create_subagent creates L3 subagent."""
        subagent = create_subagent("l3")

        assert isinstance(subagent, L3MeasurementSubagent)

    def test_create_l4_subagent(self) -> None:
        """create_subagent creates L4 subagent."""
        subagent = create_subagent("l4")

        assert isinstance(subagent, L4AnalysisSubagent)

    def test_create_subagent_case_insensitive(self) -> None:
        """create_subagent handles uppercase layer names."""
        subagent_upper = create_subagent("L2")
        subagent_mixed = create_subagent("L3")
        subagent_lower = create_subagent("l4")

        assert isinstance(subagent_upper, L2EnvironmentSubagent)
        assert isinstance(subagent_mixed, L3MeasurementSubagent)
        assert isinstance(subagent_lower, L4AnalysisSubagent)

    def test_create_subagent_with_model(self) -> None:
        """create_subagent accepts model parameter."""
        subagent = create_subagent("l2", model="claude-opus-4-20250514")

        assert subagent.model == "claude-opus-4-20250514"

    def test_create_subagent_with_compact_prompt(self) -> None:
        """create_subagent accepts compact_prompt parameter."""
        subagent_normal = create_subagent("l2", compact_prompt=False)
        subagent_compact = create_subagent("l2", compact_prompt=True)

        assert subagent_normal.system_prompt != subagent_compact.system_prompt

    def test_create_subagent_invalid_layer(self) -> None:
        """create_subagent raises ValueError for invalid layer."""
        with pytest.raises(ValueError) as exc_info:
            create_subagent("l1")

        assert "Unknown layer" in str(exc_info.value)
        assert "l2, l3, l4" in str(exc_info.value)

    def test_create_subagent_invalid_layer_other(self) -> None:
        """create_subagent raises ValueError for other invalid layer names."""
        with pytest.raises(ValueError):
            create_subagent("l5")

        with pytest.raises(ValueError):
            create_subagent("invalid")

        with pytest.raises(ValueError):
            create_subagent("")


class TestSubagentInvokeIntegration:
    """Integration tests for subagent invoke methods (mocked SDK)."""

    @pytest.mark.asyncio
    @patch("netsherlock.agents.subagents.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.subagents.Agent")
    async def test_l2_invoke_calls_agent(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """L2 invoke calls Claude Agent SDK."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        subagent = L2EnvironmentSubagent(settings=mock_settings)

        context = {
            "alertname": "VMNetworkLatency",
            "instance": "192.168.1.10:9100",
        }

        # Should raise NotImplementedError when parsing result
        with pytest.raises(NotImplementedError):
            await subagent.invoke(context)

        mock_agent.assert_called_once()
        mock_query.assert_called_once()

    @pytest.mark.asyncio
    @patch("netsherlock.agents.subagents.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.subagents.Agent")
    async def test_l3_invoke_calls_agent(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """L3 invoke calls Claude Agent SDK."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        subagent = L3MeasurementSubagent(settings=mock_settings)

        environment = NetworkEnvironment(
            problem_type=ProblemType.VM_NETWORK_LATENCY,
            measurement_type="vm_latency",
            source=NodeEnvironment(node_ip="192.168.1.10"),
            destination=NodeEnvironment(node_ip="192.168.1.20"),
        )

        # Should raise NotImplementedError when parsing result
        with pytest.raises(NotImplementedError):
            await subagent.invoke(environment)

        mock_agent.assert_called_once()
        mock_query.assert_called_once()

    @pytest.mark.asyncio
    @patch("netsherlock.agents.subagents.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.subagents.Agent")
    async def test_l4_invoke_calls_agent(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """L4 invoke calls Claude Agent SDK."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        subagent = L4AnalysisSubagent(settings=mock_settings)

        histogram = LatencyHistogram(
            p50_us=100.0, p95_us=200.0, p99_us=300.0, max_us=500.0
        )
        measurements = MeasurementResult(
            measurement_id="test-123",
            measurement_type="vm_latency",
            timestamp="2024-01-15T10:00:00Z",
            duration_seconds=30.0,
            sample_count=1000,
            segments=[
                LatencySegment(name="segment_a", layer="vm_internal", histogram=histogram)
            ],
            total_latency=histogram,
        )

        # Should raise NotImplementedError when parsing result
        with pytest.raises(NotImplementedError):
            await subagent.invoke(measurements)

        mock_agent.assert_called_once()
        mock_query.assert_called_once()


class TestSubagentSystemPrompts:
    """Tests for subagent system prompts."""

    def test_l2_has_system_prompt(self, mock_settings: MagicMock) -> None:
        """L2 subagent has a system prompt."""
        subagent = L2EnvironmentSubagent(settings=mock_settings)

        assert subagent.system_prompt is not None
        assert len(subagent.system_prompt) > 0

    def test_l3_has_system_prompt(self, mock_settings: MagicMock) -> None:
        """L3 subagent has a system prompt."""
        subagent = L3MeasurementSubagent(settings=mock_settings)

        assert subagent.system_prompt is not None
        assert len(subagent.system_prompt) > 0

    def test_l4_has_system_prompt(self, mock_settings: MagicMock) -> None:
        """L4 subagent has a system prompt."""
        subagent = L4AnalysisSubagent(settings=mock_settings)

        assert subagent.system_prompt is not None
        assert len(subagent.system_prompt) > 0

    def test_compact_prompts_are_shorter(self, mock_settings: MagicMock) -> None:
        """Compact prompts are shorter than normal prompts."""
        l2_normal = L2EnvironmentSubagent(settings=mock_settings, compact_prompt=False)
        l2_compact = L2EnvironmentSubagent(settings=mock_settings, compact_prompt=True)

        assert len(l2_compact.system_prompt) < len(l2_normal.system_prompt)

        l3_normal = L3MeasurementSubagent(settings=mock_settings, compact_prompt=False)
        l3_compact = L3MeasurementSubagent(settings=mock_settings, compact_prompt=True)

        assert len(l3_compact.system_prompt) < len(l3_normal.system_prompt)

        l4_normal = L4AnalysisSubagent(settings=mock_settings, compact_prompt=False)
        l4_compact = L4AnalysisSubagent(settings=mock_settings, compact_prompt=True)

        assert len(l4_compact.system_prompt) < len(l4_normal.system_prompt)
