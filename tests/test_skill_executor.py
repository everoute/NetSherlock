"""Tests for SkillExecutor."""

import pytest

from netsherlock.core.skill_executor import (
    MockSkillExecutor,
    SkillExecutor,
    SkillResult,
    create_mock_analysis_response,
    create_mock_env_collector_response,
    create_mock_measurement_response,
)


class TestSkillResult:
    """Tests for SkillResult dataclass."""

    def test_default_values(self):
        """Default values are correct."""
        result = SkillResult()
        assert result.status == "success"
        assert result.data == {}
        assert result.raw_outputs == []
        assert result.error is None

    def test_is_success(self):
        """is_success property works."""
        success = SkillResult(status="success")
        assert success.is_success is True

        error = SkillResult(status="error")
        assert error.is_success is False

        timeout = SkillResult(status="timeout")
        assert timeout.is_success is False

    def test_get_data(self):
        """get method works."""
        result = SkillResult(data={"key": "value", "number": 42})

        assert result.get("key") == "value"
        assert result.get("number") == 42
        assert result.get("missing") is None
        assert result.get("missing", "default") == "default"

    def test_with_error(self):
        """Error result."""
        result = SkillResult(status="error", error="Something went wrong")
        assert result.is_success is False
        assert result.error == "Something went wrong"


class TestSkillExecutor:
    """Tests for SkillExecutor class."""

    def test_init_default_values(self, tmp_path):
        """Initialize with default values."""
        executor = SkillExecutor(project_path=tmp_path)

        assert executor.project_path == tmp_path
        assert executor.allowed_tools == ["Skill", "Read", "Write", "Bash"]
        assert executor.default_timeout == 300.0

    def test_init_custom_values(self, tmp_path):
        """Initialize with custom values."""
        executor = SkillExecutor(
            project_path=tmp_path,
            allowed_tools=["Bash", "Read"],
            default_timeout=60.0,
        )

        assert executor.allowed_tools == ["Bash", "Read"]
        assert executor.default_timeout == 60.0

    def test_build_skill_prompt_simple(self, tmp_path):
        """Build prompt with simple parameters."""
        executor = SkillExecutor(project_path=tmp_path)

        prompt = executor._build_skill_prompt(
            "test-skill",
            {"param1": "value1", "param2": 42},
        )

        assert "test-skill" in prompt
        assert "param1: value1" in prompt
        assert "param2: 42" in prompt

    def test_build_skill_prompt_nested_dict(self, tmp_path):
        """Build prompt with nested dictionary parameters."""
        executor = SkillExecutor(project_path=tmp_path)

        prompt = executor._build_skill_prompt(
            "test-skill",
            {
                "simple": "value",
                "nested": {"key1": "val1", "key2": "val2"},
            },
        )

        assert "nested:" in prompt
        assert "key1: val1" in prompt
        assert "key2: val2" in prompt

    def test_build_skill_prompt_list(self, tmp_path):
        """Build prompt with list parameters."""
        executor = SkillExecutor(project_path=tmp_path)

        prompt = executor._build_skill_prompt(
            "test-skill",
            {"items": ["item1", "item2", "item3"]},
        )

        assert "items:" in prompt
        assert "- item1" in prompt
        assert "- item2" in prompt

    def test_parse_skill_output_empty(self, tmp_path):
        """Parse empty output."""
        executor = SkillExecutor(project_path=tmp_path)

        result = executor._parse_skill_output([])

        assert result.status == "success"
        assert result.raw_outputs == []

    def test_parse_skill_output_with_text_block(self, tmp_path):
        """Parse output with TextBlock in content list (real SDK format)."""
        executor = SkillExecutor(project_path=tmp_path)

        class MockTextBlock:
            text = "test content"

        class MockAssistantMessage:
            content = [MockTextBlock()]

        result = executor._parse_skill_output([MockAssistantMessage()])

        assert result.status == "success"
        assert result.data.get("text_content") == "test content"

    def test_parse_skill_output_with_json_in_text(self, tmp_path):
        """Parse output with JSON embedded in TextBlock."""
        executor = SkillExecutor(project_path=tmp_path)

        class MockTextBlock:
            text = '{"key": "value", "number": 42}'

        class MockAssistantMessage:
            content = [MockTextBlock()]

        result = executor._parse_skill_output([MockAssistantMessage()])

        assert result.data.get("key") == "value"
        assert result.data.get("number") == 42

    def test_parse_skill_output_with_tool_result(self, tmp_path):
        """Parse output with ToolResultBlock (tool execution result)."""
        executor = SkillExecutor(project_path=tmp_path)

        class MockToolResultBlock:
            tool_use_id = "test-id"
            content = '{"qemu_pid": 12345, "vnet": "vnet0"}'

        class MockUserMessage:
            content = [MockToolResultBlock()]

        result = executor._parse_skill_output([MockUserMessage()])

        assert result.data.get("qemu_pid") == 12345
        assert result.data.get("vnet") == "vnet0"
        assert "tool_outputs" in result.data

    def test_parse_skill_output_with_result_message(self, tmp_path):
        """Parse output with ResultMessage (final result)."""
        executor = SkillExecutor(project_path=tmp_path)

        class MockResultMessage:
            result = "Final result text"
            structured_output = None

        result = executor._parse_skill_output([MockResultMessage()])

        assert result.data.get("final_result") == "Final result text"


class TestMockSkillExecutor:
    """Tests for MockSkillExecutor."""

    @pytest.mark.asyncio
    async def test_default_response(self):
        """Default response is returned."""
        executor = MockSkillExecutor()

        result = await executor.invoke("any-skill", {"param": "value"})

        assert result.is_success
        assert result.data.get("mock") is True

    @pytest.mark.asyncio
    async def test_custom_response(self):
        """Custom responses are returned for specific skills."""
        custom_response = SkillResult(
            status="success",
            data={"custom": "data"},
        )
        executor = MockSkillExecutor(responses={"my-skill": custom_response})

        result = await executor.invoke("my-skill", {})

        assert result.data.get("custom") == "data"

    @pytest.mark.asyncio
    async def test_add_response(self):
        """add_response method works."""
        executor = MockSkillExecutor()
        executor.add_response(
            "new-skill",
            SkillResult(data={"added": True}),
        )

        result = await executor.invoke("new-skill", {})

        assert result.data.get("added") is True

    @pytest.mark.asyncio
    async def test_invocations_recorded(self):
        """Invocations are recorded."""
        executor = MockSkillExecutor()

        await executor.invoke("skill-1", {"a": 1})
        await executor.invoke("skill-2", {"b": 2})
        await executor.invoke("skill-1", {"c": 3})

        assert len(executor.invocations) == 3
        assert executor.invocations[0] == ("skill-1", {"a": 1})
        assert executor.invocations[1] == ("skill-2", {"b": 2})

    @pytest.mark.asyncio
    async def test_get_invocations_filtered(self):
        """get_invocations filters by skill name."""
        executor = MockSkillExecutor()

        await executor.invoke("skill-1", {"a": 1})
        await executor.invoke("skill-2", {"b": 2})
        await executor.invoke("skill-1", {"c": 3})

        skill_1_invocations = executor.get_invocations("skill-1")

        assert len(skill_1_invocations) == 2
        assert skill_1_invocations[0][1] == {"a": 1}
        assert skill_1_invocations[1][1] == {"c": 3}

    @pytest.mark.asyncio
    async def test_clear_invocations(self):
        """clear_invocations clears the list."""
        executor = MockSkillExecutor()

        await executor.invoke("skill-1", {})
        await executor.invoke("skill-2", {})
        executor.clear_invocations()

        assert len(executor.invocations) == 0

    @pytest.mark.asyncio
    async def test_custom_default_response(self):
        """Custom default response is used."""
        default = SkillResult(status="error", error="Default error")
        executor = MockSkillExecutor(default_response=default)

        result = await executor.invoke("unknown-skill", {})

        assert result.status == "error"
        assert result.error == "Default error"


class TestMockResponseFactories:
    """Tests for mock response factory functions."""

    def test_create_mock_env_collector_response_defaults(self):
        """create_mock_env_collector_response with defaults."""
        response = create_mock_env_collector_response()

        assert response.is_success
        assert response.data.get("vm_uuid") == "test-uuid"
        assert response.data.get("qemu_pid") == 12345
        assert len(response.data.get("nics", [])) == 1

        nic = response.data["nics"][0]
        assert nic["host_vnet"] == "vnet0"
        assert nic["ovs_bridge"] == "ovsbr-test"

    def test_create_mock_env_collector_response_custom(self):
        """create_mock_env_collector_response with custom values."""
        response = create_mock_env_collector_response(
            vm_uuid="custom-uuid",
            qemu_pid=99999,
            vnet="vnet5",
        )

        assert response.data.get("vm_uuid") == "custom-uuid"
        assert response.data.get("qemu_pid") == 99999
        assert response.data["nics"][0]["host_vnet"] == "vnet5"

    def test_create_mock_measurement_response_defaults(self):
        """create_mock_measurement_response with defaults."""
        response = create_mock_measurement_response()

        assert response.is_success
        assert response.data.get("total_rtt_us") == 2000.0

        segments = response.data.get("segments", {})
        assert "A" in segments
        assert "B" in segments
        assert "M" in segments

        log_files = response.data.get("log_files", [])
        assert len(log_files) == 8

    def test_create_mock_measurement_response_custom(self):
        """create_mock_measurement_response with custom values."""
        custom_segments = {"A": 50.0, "B": 100.0}
        response = create_mock_measurement_response(
            total_rtt_us=1000.0,
            segments=custom_segments,
        )

        assert response.data.get("total_rtt_us") == 1000.0
        assert response.data.get("segments") == custom_segments

    def test_create_mock_analysis_response_defaults(self):
        """create_mock_analysis_response with defaults."""
        response = create_mock_analysis_response()

        assert response.is_success
        assert response.data.get("primary_contributor") == "host_ovs"
        assert response.data.get("confidence") == 0.85

        causes = response.data.get("probable_causes", [])
        assert len(causes) == 1
        assert causes[0]["layer"] == "host_ovs"

        recommendations = response.data.get("recommendations", [])
        assert len(recommendations) == 1
        assert recommendations[0]["priority"] == "high"

    def test_create_mock_analysis_response_custom(self):
        """create_mock_analysis_response with custom values."""
        response = create_mock_analysis_response(
            primary_contributor="vm_kernel",
            confidence=0.95,
        )

        assert response.data.get("primary_contributor") == "vm_kernel"
        assert response.data.get("confidence") == 0.95


class TestSkillExecutorIntegration:
    """Integration tests for MockSkillExecutor with factory functions."""

    @pytest.mark.asyncio
    async def test_full_diagnosis_workflow_mock(self):
        """Simulate a full diagnosis workflow with mocks."""
        # Setup mock executor with responses for each skill
        executor = MockSkillExecutor(
            responses={
                "network-env-collector": create_mock_env_collector_response(
                    vm_uuid="sender-uuid",
                    qemu_pid=12345,
                ),
                "vm-latency-measurement": create_mock_measurement_response(
                    total_rtt_us=2500.0,
                ),
                "vm-latency-analysis": create_mock_analysis_response(
                    primary_contributor="host_ovs",
                    confidence=0.90,
                ),
            }
        )

        # Step 1: Collect environment
        env_result = await executor.invoke(
            "network-env-collector",
            {"mode": "vm", "uuid": "sender-uuid"},
        )
        assert env_result.is_success
        assert env_result.data.get("qemu_pid") == 12345

        # Step 2: Execute measurement
        measurement_result = await executor.invoke(
            "vm-latency-measurement",
            {
                "sender_vm_ip": "10.0.0.1",
                "receiver_vm_ip": "10.0.0.2",
            },
        )
        assert measurement_result.is_success
        assert measurement_result.data.get("total_rtt_us") == 2500.0

        # Step 3: Analyze results
        analysis_result = await executor.invoke(
            "vm-latency-analysis",
            {"measurement_data": measurement_result.data},
        )
        assert analysis_result.is_success
        assert analysis_result.data.get("primary_contributor") == "host_ovs"

        # Verify all invocations recorded
        assert len(executor.invocations) == 3
        assert executor.get_invocations("network-env-collector")[0][1]["uuid"] == "sender-uuid"

    @pytest.mark.asyncio
    async def test_error_handling_in_workflow(self):
        """Test error handling when a skill fails."""
        executor = MockSkillExecutor(
            responses={
                "network-env-collector": SkillResult(
                    status="error",
                    error="SSH connection failed",
                ),
            }
        )

        result = await executor.invoke(
            "network-env-collector",
            {"mode": "vm", "uuid": "test-uuid"},
        )

        assert not result.is_success
        assert result.status == "error"
        assert "SSH connection failed" in result.error
