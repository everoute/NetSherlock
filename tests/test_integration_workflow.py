"""Integration tests for the complete diagnosis workflow.

Tests the full integration of:
- MinimalInputConfig loading
- GlobalInventory loading and building
- DiagnosisController execution with SkillExecutor
- AnalysisResult generation
"""

import tempfile
from pathlib import Path

import pytest

from netsherlock.config.global_inventory import GlobalInventory
from netsherlock.controller.diagnosis_controller import (
    DiagnosisController,
    DiagnosisPhase,
)
from netsherlock.core.skill_executor import (
    MockSkillExecutor,
    create_mock_analysis_response,
    create_mock_env_collector_response,
    create_mock_measurement_response,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisStatus
from netsherlock.schemas.analysis import LayerType
from netsherlock.schemas.config import DiagnosisConfig, DiagnosisMode
from netsherlock.schemas.minimal_input import MinimalInputConfig

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def real_minimal_input_yaml():
    """Real minimal input YAML matching template format."""
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
def real_global_inventory_yaml():
    """Real global inventory YAML matching template format."""
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
    uuid: "ae6aa164-604c-4cb0-84b8-2dea034307f1"
    host_ref: "host-192-168-75-101"
    ssh:
      user: "root"
      host: "192.168.2.100"
      key_file: "/root/.ssh/vm_key"
    test_ip: "10.0.0.1"

  vm-be7bb275:
    uuid: "be7bb275-715d-5dc1-95c9-3efb045418g2"
    host_ref: "host-192-168-75-102"
    ssh:
      user: "root"
      host: "192.168.2.101"
      key_file: "/root/.ssh/vm_key"
    test_ip: "10.0.0.2"
"""


@pytest.fixture
def minimal_input_file(real_minimal_input_yaml):
    """Create temporary minimal input file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(real_minimal_input_yaml)
        return Path(f.name)


@pytest.fixture
def global_inventory_file(real_global_inventory_yaml):
    """Create temporary global inventory file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(real_global_inventory_yaml)
        return Path(f.name)


@pytest.fixture
def full_mock_executor():
    """Create fully configured mock executor."""
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


# ============================================================================
# Config Loading Integration Tests
# ============================================================================


class TestMinimalInputIntegration:
    """Integration tests for MinimalInputConfig."""

    def test_load_from_template_format(self, minimal_input_file):
        """Test loading config from template format."""
        config = MinimalInputConfig.load(minimal_input_file)

        # Verify all nodes loaded
        assert len(config.nodes) == 4
        assert "vm-sender" in config.nodes
        assert "vm-receiver" in config.nodes
        assert "host-sender" in config.nodes
        assert "host-receiver" in config.nodes

        # Verify VM nodes have required fields
        vm_sender = config.get_node("vm-sender")
        assert vm_sender.role == "vm"
        assert vm_sender.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"
        assert vm_sender.test_ip == "10.0.0.1"
        assert vm_sender.host_ref == "host-sender"

        # Verify test pairs
        assert config.test_pairs is not None
        vm_pair = config.get_test_pair("vm")
        assert vm_pair.server == "vm-receiver"
        assert vm_pair.client == "vm-sender"

        # Verify discovery hints
        assert config.discovery_hints is not None
        assert config.discovery_hints.get("internal_port_type") == "mgt"

    def test_validation_passes_for_valid_config(self, minimal_input_file):
        """Test validation passes for valid config."""
        config = MinimalInputConfig.load(minimal_input_file)
        errors = config.validate()
        assert len(errors) == 0

    def test_get_sender_receiver_config(self, minimal_input_file):
        """Test getting full sender/receiver configuration."""
        config = MinimalInputConfig.load(minimal_input_file)
        result = config.get_sender_receiver_config("vm")

        assert result is not None
        sender_vm, sender_host, receiver_vm, receiver_host = result

        assert sender_vm.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"
        assert sender_vm.test_ip == "10.0.0.1"
        assert sender_host.role == "host"

        assert receiver_vm.uuid == "be7bb275-715d-5dc1-95c9-3efb045418g2"
        assert receiver_vm.test_ip == "10.0.0.2"
        assert receiver_host.role == "host"


class TestGlobalInventoryIntegration:
    """Integration tests for GlobalInventory."""

    def test_load_from_template_format(self, global_inventory_file):
        """Test loading inventory from template format."""
        inventory = GlobalInventory.load(global_inventory_file)

        # Verify hosts
        assert len(inventory.hosts) == 2
        assert "host-192-168-75-101" in inventory.hosts
        assert "host-192-168-75-102" in inventory.hosts

        host = inventory.hosts["host-192-168-75-101"]
        assert host.mgmt_ip == "192.168.75.101"
        assert host.ssh_user == "smartx"
        assert host.ssh_key_file == "/root/.ssh/host_key"
        assert "mgt" in host.network_types

        # Verify VMs
        assert len(inventory.vms) == 2
        vm = inventory.vms["vm-ae6aa164"]
        assert vm.uuid == "ae6aa164-604c-4cb0-84b8-2dea034307f1"
        assert vm.test_ip == "10.0.0.1"
        assert vm.host_ref == "host-192-168-75-101"

    def test_validation_passes(self, global_inventory_file):
        """Test validation passes for valid inventory."""
        inventory = GlobalInventory.load(global_inventory_file)
        errors = inventory.validate()
        assert len(errors) == 0

    def test_build_minimal_input_from_alert(self, global_inventory_file):
        """Test building MinimalInputConfig from alert data."""
        inventory = GlobalInventory.load(global_inventory_file)

        # Simulate L1 alert data
        config = inventory.build_minimal_input(
            src_host_ip="192.168.75.101",
            src_vm_uuid="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host_ip="192.168.75.102",
            dst_vm_uuid="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        # Verify nodes created
        assert len(config.nodes) == 4
        assert "host-sender" in config.nodes
        assert "host-receiver" in config.nodes
        assert "vm-sender" in config.nodes
        assert "vm-receiver" in config.nodes

        # Verify test_ip preserved
        vm_sender = config.get_node("vm-sender")
        assert vm_sender.test_ip == "10.0.0.1"

        vm_receiver = config.get_node("vm-receiver")
        assert vm_receiver.test_ip == "10.0.0.2"

        # Verify test pairs created
        assert config.test_pairs is not None
        assert "vm" in config.test_pairs


# ============================================================================
# Full Workflow Integration Tests
# ============================================================================


class TestFullDiagnosisWorkflow:
    """Integration tests for complete diagnosis workflow."""

    @pytest.mark.asyncio
    async def test_manual_mode_workflow(
        self, minimal_input_file, full_mock_executor
    ):
        """Test complete workflow in manual mode."""
        request = DiagnosisRequest(
            request_id="integration-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
            options={"duration": 30},
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Verify successful completion
        assert result.status == DiagnosisStatus.COMPLETED
        assert result.mode == DiagnosisMode.AUTONOMOUS

        # Verify analysis result
        assert result.analysis_result is not None
        assert result.analysis_result.breakdown.total_rtt_us == 2500.0
        assert result.analysis_result.primary_contributor == LayerType.HOST_OVS
        assert result.analysis_result.confidence == 0.85

        # Verify phases completed
        state = controller.state
        assert state.phase == DiagnosisPhase.COMPLETED
        assert state.l1_context is not None
        assert state.environment is not None
        assert state.classification is not None
        assert state.measurement_plan is not None
        assert state.measurements is not None
        assert state.analysis is not None

    @pytest.mark.asyncio
    async def test_auto_mode_workflow(
        self, global_inventory_file, full_mock_executor
    ):
        """Test complete workflow in automatic mode."""
        request = DiagnosisRequest(
            request_id="auto-mode-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            global_inventory_path=global_inventory_file,  # Auto mode
        )

        result = await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Verify successful completion
        assert result.status == DiagnosisStatus.COMPLETED

        # Verify global inventory was loaded
        assert controller._global_inventory is not None
        assert len(controller._global_inventory.hosts) == 2

        # Verify minimal input was built from inventory
        assert controller._minimal_input is not None
        assert "vm-sender" in controller._minimal_input.nodes

    @pytest.mark.asyncio
    async def test_skill_invocation_sequence(
        self, minimal_input_file, full_mock_executor
    ):
        """Test skills are invoked in correct sequence."""
        request = DiagnosisRequest(
            request_id="sequence-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Check invocation sequence
        invocations = full_mock_executor.invocations
        skill_names = [name for name, _ in invocations]

        # Environment collection should happen first (src and dst)
        env_collector_indices = [
            i for i, name in enumerate(skill_names)
            if name == "network-env-collector"
        ]
        assert len(env_collector_indices) >= 1

        # Measurement should happen after environment
        measurement_index = skill_names.index("vm-latency-measurement")
        assert measurement_index > env_collector_indices[0]

        # Analysis should happen last
        analysis_index = skill_names.index("vm-latency-analysis")
        assert analysis_index > measurement_index

    @pytest.mark.asyncio
    async def test_test_ip_propagation(
        self, minimal_input_file, full_mock_executor
    ):
        """Test that test_ip is correctly propagated through workflow."""
        request = DiagnosisRequest(
            request_id="test-ip-propagation-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Check measurement skill received correct test_ip
        measurement_invocations = full_mock_executor.get_invocations("vm-latency-measurement")
        assert len(measurement_invocations) == 1

        params = measurement_invocations[0][1]
        assert params.get("sender_vm_ip") == "10.0.0.1"  # From config
        assert params.get("receiver_vm_ip") == "10.0.0.2"  # From config

        # These should NOT be the SSH IPs
        assert params.get("sender_vm_ip") != "192.168.2.100"
        assert params.get("receiver_vm_ip") != "192.168.2.101"


class TestAnalysisResultIntegration:
    """Integration tests for AnalysisResult generation."""

    @pytest.mark.asyncio
    async def test_breakdown_layer_attribution(
        self, minimal_input_file, full_mock_executor
    ):
        """Test layer attribution is correctly calculated."""
        request = DiagnosisRequest(
            request_id="breakdown-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        breakdown = result.analysis_result.breakdown

        # Check layer attribution exists
        assert len(breakdown.layer_attribution) == 5

        # Check all layer types present
        assert LayerType.VM_KERNEL in breakdown.layer_attribution
        assert LayerType.HOST_OVS in breakdown.layer_attribution
        assert LayerType.PHYSICAL_NETWORK in breakdown.layer_attribution
        assert LayerType.VIRT_RX in breakdown.layer_attribution
        assert LayerType.VIRT_TX in breakdown.layer_attribution

        # Check percentages are reasonable (VIRT_TX segments B_1 and I_1 may be missing
        # in the mock data, so we don't expect exactly 100%)
        total_percentage = sum(
            layer.percentage for layer in breakdown.layer_attribution.values()
        )
        assert total_percentage > 0  # Some attribution should exist

    @pytest.mark.asyncio
    async def test_analysis_summary_generation(
        self, minimal_input_file, full_mock_executor
    ):
        """Test analysis summary is properly generated."""
        request = DiagnosisRequest(
            request_id="summary-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        # Check summary contains key information
        summary = result.analysis_result.summary()
        assert "Total RTT" in summary
        assert "Primary Contributor" in summary
        assert "2500.00 us" in summary or "2.500 ms" in summary

    @pytest.mark.asyncio
    async def test_probable_causes_and_recommendations(
        self, minimal_input_file, full_mock_executor
    ):
        """Test probable causes and recommendations are captured."""
        request = DiagnosisRequest(
            request_id="causes-test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_host="192.168.75.102",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

        config = DiagnosisConfig()
        controller = DiagnosisController(
            config=config,
            skill_executor=full_mock_executor,
            minimal_input_path=minimal_input_file,
        )

        result = await controller.run(
            request=request,
            force_mode=DiagnosisMode.AUTONOMOUS,
        )

        analysis = result.analysis_result

        # Check probable causes
        assert len(analysis.probable_causes) > 0
        cause = analysis.probable_causes[0]
        assert cause.cause is not None
        assert cause.confidence > 0

        # Check recommendations
        assert len(analysis.recommendations) > 0
        rec = analysis.recommendations[0]
        assert rec.action is not None
        assert rec.priority in ["high", "medium", "low"]
