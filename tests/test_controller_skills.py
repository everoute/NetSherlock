"""Tests for DiagnosisController skill-based workflow.

Tests the integration of SkillExecutor with DiagnosisController.
"""

import tempfile
from pathlib import Path

import pytest

from netsherlock.controller.diagnosis_controller import DiagnosisController
from netsherlock.core.skill_executor import (
    MockSkillExecutor,
    SkillResult,
    create_mock_analysis_response,
    create_mock_env_collector_response,
    create_mock_measurement_response,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisStatus
from netsherlock.schemas.config import DiagnosisConfig, DiagnosisMode


@pytest.fixture
def sample_minimal_input_yaml():
    """Sample minimal input YAML."""
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
"""


@pytest.fixture
def minimal_input_file(sample_minimal_input_yaml):
    """Create temporary minimal input file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(sample_minimal_input_yaml)
        return Path(f.name)


@pytest.fixture
def cross_node_vm_request():
    """Create cross-node VM diagnosis request."""
    return DiagnosisRequest(
        request_id="test-request-001",
        request_type="latency",
        network_type="vm",
        src_host="192.168.75.101",
        src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        dst_host="192.168.75.102",
        dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        options={"duration": 30},
    )


@pytest.fixture
def mock_skill_executor():
    """Create mock skill executor with predefined responses."""
    return MockSkillExecutor(
        responses={
            "network-env-collector": create_mock_env_collector_response(
                vm_uuid="ae6aa164-604c-4cb0-84b8-2dea034307f1",
                qemu_pid=12345,
                vnet="vnet0",
            ),
            "vm-latency-measurement": create_mock_measurement_response(
                total_rtt_us=2500.0,
                segments={
                    "A": 100.0,
                    "B": 200.0,
                    "C_J": 300.0,
                    "D": 150.0,
                    "E": 250.0,
                    "F": 120.0,
                    "G": 80.0,
                    "H": 100.0,
                    "I": 180.0,
                    "K": 170.0,
                    "L": 200.0,
                    "M": 150.0,
                },
            ),
            "vm-latency-analysis": create_mock_analysis_response(
                primary_contributor="host_ovs",
                confidence=0.85,
            ),
        }
    )


class TestControllerWithSkillExecutor:
    """Tests for DiagnosisController with skill executor integration."""

    @pytest.mark.asyncio
    async def test_autonomous_workflow_with_mock_skills(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test complete autonomous workflow with mock skills."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        assert result.status == DiagnosisStatus.COMPLETED
        assert result.mode == DiagnosisMode.AUTONOMOUS

        # Verify skill invocations
        invocations = mock_skill_executor.invocations
        skill_names = [name for name, _ in invocations]

        # Should have called environment collector, measurement, and analysis
        assert "network-env-collector" in skill_names
        assert "vm-latency-measurement" in skill_names
        assert "vm-latency-analysis" in skill_names

    @pytest.mark.asyncio
    async def test_environment_collection_uses_test_ip(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test that environment collection correctly uses test_ip."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Check measurement parameters include test_ip
        measurement_invocations = mock_skill_executor.get_invocations("vm-latency-measurement")
        assert len(measurement_invocations) == 1

        params = measurement_invocations[0][1]
        assert params.get("sender_vm_ip") == "10.0.0.1"  # test_ip from config
        assert params.get("receiver_vm_ip") == "10.0.0.2"  # test_ip from config

    @pytest.mark.asyncio
    async def test_classification_identifies_cross_node(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test problem classification identifies cross-node scenario."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        state = controller.state
        assert state is not None
        assert state.classification.get("type") == "cross_node_vm_latency"
        assert state.classification.get("is_cross_node") is True

    @pytest.mark.asyncio
    async def test_measurement_plan_uses_skill_mode(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test measurement plan uses skill mode for cross-node VM."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        state = controller.state
        assert state is not None
        assert state.measurement_plan.get("mode") == "skill"
        assert state.measurement_plan.get("skill") == "vm-latency-measurement"

    @pytest.mark.asyncio
    async def test_analysis_result_populated(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test analysis result is properly populated."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        assert result.analysis_result is not None
        assert result.analysis_result.primary_contributor is not None
        # confidence comes from the unified result, not AnalysisResult
        # (AnalysisResult.confidence is populated by LLM analysis in Phase 2)
        assert result.confidence == 0.85

        # Check breakdown was calculated
        breakdown = result.analysis_result.breakdown
        assert breakdown.total_rtt_us == 2500.0
        assert len(breakdown.segments) > 0
        assert len(breakdown.layer_attribution) > 0


class TestControllerSkillErrors:
    """Tests for error handling in skill-based workflow."""

    @pytest.mark.asyncio
    async def test_env_collection_failure_continues(
        self, minimal_input_file, cross_node_vm_request
    ):
        """Test workflow continues when env collection fails."""
        mock_executor = MockSkillExecutor(
            responses={
                "network-env-collector": SkillResult(
                    status="error",
                    error="SSH connection failed",
                ),
                "vm-latency-measurement": create_mock_measurement_response(),
                "vm-latency-analysis": create_mock_analysis_response(),
            }
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Should complete even with env collection failure
        assert result.status == DiagnosisStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_measurement_failure_skips_analysis(
        self, minimal_input_file, cross_node_vm_request
    ):
        """Test analysis is skipped when measurement fails."""
        mock_executor = MockSkillExecutor(
            responses={
                "network-env-collector": create_mock_env_collector_response(),
                "vm-latency-measurement": SkillResult(
                    status="error",
                    error="Measurement timeout",
                ),
                "vm-latency-analysis": create_mock_analysis_response(),
            }
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Check analysis was skipped
        state = controller.state
        assert state.analysis.get("status") == "skipped"
        assert "Measurement failed" in state.analysis.get("reason", "")


class TestControllerWithMinimalInput:
    """Tests for MinimalInputConfig integration."""

    @pytest.mark.asyncio
    async def test_loads_minimal_input_from_file(
        self, minimal_input_file, cross_node_vm_request, mock_skill_executor
    ):
        """Test controller loads minimal input from YAML file."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Verify minimal input was loaded
        assert controller._minimal_input is not None
        assert "vm-sender" in controller._minimal_input.nodes
        assert "vm-receiver" in controller._minimal_input.nodes

    @pytest.mark.asyncio
    async def test_fallback_without_config_file(
        self, cross_node_vm_request, mock_skill_executor
    ):
        """Test controller creates fallback config without file."""
        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            # No config file provided
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Should still complete with fallback config
        assert result.status == DiagnosisStatus.COMPLETED
        assert controller._minimal_input is not None


class TestControllerUnsupportedScenarios:
    """Tests for unsupported scenarios."""

    @pytest.mark.asyncio
    async def test_single_node_vm_not_supported(
        self, minimal_input_file, mock_skill_executor
    ):
        """Test single-node VM scenario returns unsupported plan."""
        # Single-node request (no dst_host/dst_vm)
        request = DiagnosisRequest(
            request_id="test-single-node",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        state = controller.state
        assert state.measurement_plan.get("mode") == "unsupported"

    @pytest.mark.asyncio
    async def test_system_network_not_fully_supported(
        self, minimal_input_file, mock_skill_executor
    ):
        """Test system network type returns unsupported plan."""
        request = DiagnosisRequest(
            request_id="test-system",
            request_type="latency",
            network_type="system",
            src_host="192.168.75.101",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_skill_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        state = controller.state
        assert state.measurement_plan.get("mode") == "unsupported"


class TestControllerBreakdownCalculation:
    """Tests for latency breakdown calculation."""

    @pytest.mark.asyncio
    async def test_breakdown_segments_parsed(
        self, minimal_input_file, cross_node_vm_request
    ):
        """Test segments are correctly parsed into breakdown."""
        mock_executor = MockSkillExecutor(
            responses={
                "network-env-collector": create_mock_env_collector_response(),
                "vm-latency-measurement": SkillResult(
                    status="success",
                    data={
                        "total_rtt_us": 1000.0,
                        "segments": {
                            "A": 100.0,
                            "B": {"value_us": 200.0, "source": "bpf_tool"},
                            "C_J": 300.0,
                        },
                    },
                ),
                "vm-latency-analysis": create_mock_analysis_response(),
            }
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        breakdown = result.analysis_result.breakdown
        assert breakdown.total_rtt_us == 1000.0

        # Check segment parsing
        assert "A" in breakdown.segments
        assert breakdown.segments["A"].value_us == 100.0

        # Check dict-format segment
        assert "B" in breakdown.segments
        assert breakdown.segments["B"].value_us == 200.0
        assert breakdown.segments["B"].source == "bpf_tool"

    @pytest.mark.asyncio
    async def test_layer_attribution_calculated(
        self, minimal_input_file, cross_node_vm_request
    ):
        """Test layer attribution is calculated from segments."""
        mock_executor = MockSkillExecutor(
            responses={
                "network-env-collector": create_mock_env_collector_response(),
                "vm-latency-measurement": create_mock_measurement_response(
                    total_rtt_us=2000.0,
                    segments={
                        "A": 100.0,  # VM kernel
                        "F": 100.0,  # VM kernel
                        "B": 200.0,  # Host OVS
                        "D": 200.0,  # Host OVS
                    },
                ),
                "vm-latency-analysis": create_mock_analysis_response(),
            }
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=cross_node_vm_request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        breakdown = result.analysis_result.breakdown

        # Check layer attribution exists
        assert len(breakdown.layer_attribution) > 0

        # Check primary contributor can be determined
        primary = breakdown.get_primary_contributor()
        assert primary is not None
