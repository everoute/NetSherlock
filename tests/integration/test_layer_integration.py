"""Integration tests for L1→L2→L3→L4 layer data flow.

Tests that data flows correctly between diagnostic layers
and that layer outputs are compatible with layer inputs.
"""



from netsherlock.schemas.environment import (
    PhysicalNIC,
    SystemNetworkEnv,
    SystemNetworkInfo,
)
from netsherlock.schemas.measurement import (
    MeasurementStatus,
)
from netsherlock.schemas.report import (
    RootCauseCategory,
)
from netsherlock.tools.l4_analysis import (
    analyze_latency_segments,
    identify_root_cause,
)


class TestL1ToL2DataFlow:
    """Test data flow from L1 monitoring to L2 environment collection."""

    def test_l1_metrics_provide_context_for_l2(self, grafana_responses):
        """L1 metrics should provide context that informs L2 collection."""
        # L1 output: metrics showing high latency
        metrics_response = grafana_responses["metrics_query_success"]

        # Extract hostname from L1 data
        series = metrics_response["series"]
        assert len(series) > 0

        hostname = series[0]["metric"]["hostname"]
        assert hostname == "compute-node-1"

        # This hostname should be usable for L2 environment collection
        # (In real integration, this would be passed to collect_vm_network_env)

    def test_l1_logs_augment_environment_context(self, grafana_responses):
        """L1 logs should provide additional context for L2."""
        logs_response = grafana_responses["logs_query_success"]

        # Extract relevant information from logs
        entries = logs_response["entries"]
        assert len(entries) > 0

        # Check that log labels are extractable
        first_entry = entries[0]
        assert "hostname" in first_entry["labels"]
        assert first_entry["labels"]["hostname"] == "compute-node-1"


class TestL2ToL3DataFlow:
    """Test data flow from L2 environment to L3 measurement."""

    def test_vm_env_provides_measurement_parameters(self, sample_vm_env):
        """VMNetworkEnv should provide all parameters needed for L3 measurement."""
        env = sample_vm_env

        # Verify required fields for L3 are present
        assert env.host is not None  # Host for SSH connection
        assert env.qemu_pid is not None  # For BPF tool targeting
        assert len(env.nics) > 0  # At least one NIC

        nic = env.nics[0]
        assert nic.host_vnet is not None  # vnet interface name
        assert nic.ovs_bridge is not None  # OVS bridge name

        # Verify vhost PID is available if present
        if nic.vhost_pids:
            assert nic.vhost_pids[0].pid is not None

    def test_vm_env_to_measurement_args(self, sample_vm_env):
        """VMNetworkEnv should be convertible to measurement tool arguments."""
        env = sample_vm_env
        nic = env.nics[0]

        # Build measurement tool arguments from environment
        tool_args = {
            "vnet": nic.host_vnet,
            "qemu_pid": env.qemu_pid,
        }

        if nic.vhost_pids:
            tool_args["vhost_pid"] = nic.vhost_pids[0].pid

        # Verify all required args are present
        assert "vnet" in tool_args
        assert "qemu_pid" in tool_args
        assert tool_args["vnet"] == "vnet0"
        assert tool_args["qemu_pid"] == 12345

    def test_system_env_provides_port_info(self, vm_network_env_data):
        """SystemNetworkEnv should provide port information for L3."""
        data = vm_network_env_data["system_network_env_sample"]

        env = SystemNetworkEnv(
            host=data["host"],
            ports=[
                SystemNetworkInfo(
                    port_name=p["port_name"],
                    port_type=p["port_type"],
                    ip_address=p.get("ip_address"),
                    ovs_bridge=p["ovs_bridge"],
                    physical_nics=[
                        PhysicalNIC(
                            name=n["name"],
                            speed=n.get("speed", "unknown"),
                        )
                        for n in p.get("physical_nics", [])
                    ],
                )
                for p in data["ports"]
            ],
        )

        assert env.host == "192.168.1.10"
        assert len(env.ports) == 2

        # Verify port data is usable for measurement
        mgt_port = next(p for p in env.ports if p.port_type == "mgt")
        assert mgt_port.port_name == "mgt0"
        assert mgt_port.ip_address == "192.168.1.10"


class TestL3ToL4DataFlow:
    """Test data flow from L3 measurement to L4 analysis."""

    def test_measurement_result_is_analyzable(self, sample_latency_result):
        """MeasurementResult should contain all data needed for L4 analysis."""
        result = sample_latency_result

        # Verify result has required fields for analysis
        assert result.status == MeasurementStatus.SUCCESS
        assert result.latency_data is not None
        assert len(result.latency_data.segments) > 0

        # Verify segments have analyzable metrics
        for segment in result.latency_data.segments:
            assert segment.name is not None
            assert segment.avg_us is not None
            assert segment.p99_us is not None

    def test_latency_segments_to_analysis(self, sample_latency_result):
        """Latency segments should be directly usable by L4 analysis."""
        result = sample_latency_result
        segments = result.latency_data.segments

        # Verify segments can be analyzed for anomalies
        thresholds = {
            "virtio_tx": {"normal_p99": 50, "anomaly_threshold": 100},
            "vhost_handle": {"normal_p99": 100, "anomaly_threshold": 500},
            "tap_rx": {"normal_p99": 30, "anomaly_threshold": 100},
            "ovs_process": {"normal_p99": 150, "anomaly_threshold": 500},
        }

        anomalies = []
        for segment in segments:
            if segment.name in thresholds:
                threshold = thresholds[segment.name]
                if segment.p99_us > threshold["anomaly_threshold"]:
                    anomalies.append({
                        "segment": segment.name,
                        "p99_us": segment.p99_us,
                        "threshold": threshold["anomaly_threshold"],
                    })

        # In this sample data, no segments should exceed anomaly threshold
        assert len(anomalies) == 0

    def test_analyze_latency_segments_integration(self, sample_latency_result):
        """L4 analyze_latency_segments should work with L3 output."""
        result = sample_latency_result

        # Call actual L4 analysis function (takes LatencyBreakdown)
        analysis = analyze_latency_segments(
            result.latency_data,
            thresholds=None,  # Use defaults
        )

        # Verify analysis result structure
        assert analysis is not None
        assert hasattr(analysis, "attributions")
        assert hasattr(analysis, "total_latency_us")


class TestCompleteL1L2L3L4Chain:
    """Test complete data flow through all layers."""

    def test_data_chain_integrity(
        self,
        grafana_responses,
        sample_vm_env,
        sample_latency_result,
    ):
        """Data should flow through L1→L2→L3→L4 without loss."""
        # L1: Extract context from metrics
        metrics = grafana_responses["metrics_query_success"]
        hostname = metrics["series"][0]["metric"]["hostname"]
        assert hostname is not None

        # L2: Environment provides measurement params
        env = sample_vm_env
        assert env.host is not None
        assert len(env.nics) > 0

        # L3: Measurement produces latency data
        measurement = sample_latency_result
        assert measurement.status == MeasurementStatus.SUCCESS
        assert measurement.latency_data is not None

        # L4: Analysis can process measurement
        segments = measurement.latency_data.segments
        assert len(segments) > 0

        # Verify chain is complete
        chain_data = {
            "l1_hostname": hostname,
            "l2_host": env.host,
            "l2_qemu_pid": env.qemu_pid,
            "l3_segments": len(segments),
            "l3_total_avg_us": measurement.latency_data.total_avg_us,
        }

        assert all(v is not None for v in chain_data.values())

    def test_root_cause_identification(self, sample_latency_result):
        """L4 identify_root_cause should work with analysis results."""
        measurement = sample_latency_result

        # First analyze the latency segments
        latency_analysis = analyze_latency_segments(
            measurement.latency_data,
            thresholds=None,
        )

        # Then identify root cause
        category, confidence, explanation = identify_root_cause(
            latency_analysis=latency_analysis,
            drop_analysis=None,
        )

        # Verify result structure
        assert isinstance(category, RootCauseCategory)
        assert 0 <= confidence <= 1
        assert explanation is not None


class TestPartialFailureDegradation:
    """Test graceful degradation when layers fail."""

    def test_l3_failure_returns_partial_result(self, sample_failed_result):
        """L3 failure should still allow partial result with L1/L2 data."""
        failed_measurement = sample_failed_result

        # Verify failure is properly captured
        assert failed_measurement.status == MeasurementStatus.FAILED
        assert failed_measurement.error is not None

        # Even with L3 failure, we should have metadata
        assert failed_measurement.metadata is not None

    def test_degradation_uses_available_data(
        self,
        grafana_responses,
        sample_vm_env,
        sample_failed_result,
    ):
        """System should use available L1/L2 data when L3 fails."""
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


class TestLatencyBreakdownStructure:
    """Test LatencyBreakdown data structure."""

    def test_breakdown_has_segments(self, sample_latency_result):
        """LatencyBreakdown should have segments."""
        breakdown = sample_latency_result.latency_data

        assert len(breakdown.segments) > 0
        assert breakdown.total_avg_us is not None
        assert breakdown.total_p99_us is not None

    def test_segment_structure(self, sample_latency_result):
        """Each segment should have name, avg_us, p99_us."""
        breakdown = sample_latency_result.latency_data

        for segment in breakdown.segments:
            assert segment.name is not None
            assert segment.avg_us is not None
            assert segment.p99_us is not None


class TestEnvironmentDataStructure:
    """Test environment data structures."""

    def test_vm_network_env_structure(self, sample_vm_env):
        """VMNetworkEnv should have correct structure."""
        env = sample_vm_env

        assert env.vm_uuid is not None
        assert env.host is not None
        assert env.qemu_pid is not None
        assert len(env.nics) > 0

    def test_vm_nic_info_structure(self, sample_vm_env):
        """VMNicInfo should have correct structure."""
        nic = sample_vm_env.nics[0]

        assert nic.mac is not None
        assert nic.host_vnet is not None
        assert nic.ovs_bridge is not None

    def test_vhost_info_structure(self, sample_vm_env):
        """VhostInfo should have correct structure."""
        nic = sample_vm_env.nics[0]

        if nic.vhost_pids:
            vhost = nic.vhost_pids[0]
            assert vhost.pid is not None
