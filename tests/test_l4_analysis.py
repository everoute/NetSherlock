"""Tests for L4 diagnostic analysis tools.

Tests for latency analysis, drop analysis, and report generation.
"""

import pytest

from netsherlock.tools.l4_analysis import (
    analyze_latency_segments,
    analyze_packet_drops,
    generate_diagnosis_report,
    identify_root_cause,
    _get_layer_recommendation,
    DEFAULT_THRESHOLDS,
    LAYER_DEFINITIONS,
)
from netsherlock.schemas.measurement import (
    LatencyBreakdown,
    LatencySegment,
    MeasurementMetadata,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
    PacketDropResult,
    DropPoint,
)
from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.report import RootCauseCategory, Severity


class TestDefaultThresholds:
    """Tests for default threshold constants."""

    def test_thresholds_defined(self):
        """Test that default thresholds are defined."""
        assert "total_p99_warning" in DEFAULT_THRESHOLDS
        assert "total_p99_critical" in DEFAULT_THRESHOLDS
        assert "segment_anomaly_ratio" in DEFAULT_THRESHOLDS
        assert "vm_internal_baseline" in DEFAULT_THRESHOLDS

    def test_threshold_values(self):
        """Test threshold value ranges."""
        assert DEFAULT_THRESHOLDS["total_p99_warning"] < DEFAULT_THRESHOLDS["total_p99_critical"]
        assert DEFAULT_THRESHOLDS["segment_anomaly_ratio"] >= 1.0


class TestLayerDefinitions:
    """Tests for layer definition constants."""

    def test_layers_defined(self):
        """Test that all layers are defined."""
        assert "vm_internal" in LAYER_DEFINITIONS
        assert "vhost_processing" in LAYER_DEFINITIONS
        assert "host_internal" in LAYER_DEFINITIONS
        assert "physical_network" in LAYER_DEFINITIONS

    def test_layer_structure(self):
        """Test that each layer has required fields."""
        for layer_name, config in LAYER_DEFINITIONS.items():
            assert "segments" in config, f"Missing segments in {layer_name}"
            assert "description" in config, f"Missing description in {layer_name}"
            assert isinstance(config["segments"], list)


class TestAnalyzeLatencySegments:
    """Tests for analyze_latency_segments function."""

    def test_analyze_empty_breakdown(self):
        """Test analyzing empty breakdown."""
        breakdown = LatencyBreakdown(
            segments=[],
            total_avg_us=0,
            total_p99_us=0,
        )

        result = analyze_latency_segments(breakdown)

        assert result.total_latency_us == 0
        assert len(result.attributions) == 0
        assert len(result.anomalous_segments) == 0

    def test_analyze_single_segment(self):
        """Test analyzing single segment."""
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=100.0, p99_us=500.0),
            ],
            total_avg_us=100.0,
            total_p99_us=500.0,
        )

        result = analyze_latency_segments(breakdown)

        assert result.total_latency_us == 100.0
        assert len(result.attributions) >= 1

    def test_analyze_multiple_segments_by_layer(self):
        """Test analyzing segments grouped by layer."""
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=50.0, p99_us=200.0),
                LatencySegment(name="virtio_rx", avg_us=50.0, p99_us=200.0),
                LatencySegment(name="vhost_to_tap", avg_us=100.0, p99_us=400.0),
                LatencySegment(name="tap_to_ovs", avg_us=80.0, p99_us=300.0),
            ],
            total_avg_us=280.0,
            total_p99_us=1100.0,
        )

        result = analyze_latency_segments(breakdown)

        # Should group into vm_internal, vhost_processing, host_internal
        assert result.total_latency_us == 280.0
        assert len(result.attributions) >= 2

    def test_analyze_detects_anomaly(self):
        """Test that high latency is detected as anomaly."""
        # Create breakdown with very high latency in one layer
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=500.0, p99_us=2000.0),  # High
            ],
            total_avg_us=500.0,
            total_p99_us=2000.0,
        )

        result = analyze_latency_segments(breakdown)

        # Should detect anomaly (500 > 50 * 2.0 = 100)
        assert len(result.anomalous_segments) > 0

    def test_analyze_custom_thresholds(self):
        """Test analyzing with custom thresholds."""
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=100.0, p99_us=400.0),
            ],
            total_avg_us=100.0,
            total_p99_us=400.0,
        )

        # With higher baseline, should not be anomaly
        result = analyze_latency_segments(
            breakdown,
            thresholds={"vm_internal_baseline": 100, "segment_anomaly_ratio": 2.0},
        )

        # 100 is not > 100 * 2.0, so not anomaly
        anomalous = [a for a in result.attributions if a.is_anomaly]
        assert len(anomalous) == 0

    def test_analyze_calculates_excess_latency(self):
        """Test excess latency calculation."""
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=200.0, p99_us=800.0),
                LatencySegment(name="tap_to_ovs", avg_us=300.0, p99_us=1000.0),
            ],
            total_avg_us=500.0,
            total_p99_us=1800.0,
        )

        result = analyze_latency_segments(breakdown)

        # Total 500us - baseline (vm_internal=50 + host_internal=100 + others)
        assert result.baseline_latency_us > 0
        # Excess should be calculated when total > baseline
        if result.total_latency_us > result.baseline_latency_us:
            assert result.excess_latency_us is not None

    def test_analyze_percentage_calculation(self):
        """Test percentage attribution calculation."""
        breakdown = LatencyBreakdown(
            segments=[
                LatencySegment(name="virtio_tx", avg_us=100.0, p99_us=400.0),
                LatencySegment(name="tap_to_ovs", avg_us=100.0, p99_us=400.0),
            ],
            total_avg_us=200.0,
            total_p99_us=800.0,
        )

        result = analyze_latency_segments(breakdown)

        # Total percentages should sum to ~1.0
        total_percentage = sum(a.percentage for a in result.attributions)
        assert 0.99 <= total_percentage <= 1.01


class TestAnalyzePacketDrops:
    """Tests for analyze_packet_drops function."""

    def test_analyze_no_drops(self):
        """Test analyzing with no drops."""
        drop_result = PacketDropResult(
            drop_points=[],
            total_drops=0,
        )

        result = analyze_packet_drops(drop_result)

        assert result.total_drops == 0
        assert result.drop_rate == 0
        assert len(result.top_drop_locations) == 0
        assert len(result.likely_causes) == 0

    def test_analyze_single_drop_point(self):
        """Test analyzing single drop point."""
        drop_result = PacketDropResult(
            drop_points=[
                DropPoint(location="nf_hook_slow", count=50),
            ],
            total_drops=50,
        )

        result = analyze_packet_drops(drop_result)

        assert result.total_drops == 50
        assert result.drop_rate > 0
        assert "nf_hook_slow" in result.top_drop_locations
        assert len(result.likely_causes) > 0

    def test_analyze_multiple_drop_points(self):
        """Test analyzing multiple drop points."""
        drop_result = PacketDropResult(
            drop_points=[
                DropPoint(location="nf_hook_slow", count=100),
                DropPoint(location="tcp_v4_rcv", count=50),
                DropPoint(location="ip_rcv", count=25),
            ],
            total_drops=175,
        )

        result = analyze_packet_drops(drop_result)

        assert result.total_drops == 175
        # Top locations should be sorted by count
        assert result.top_drop_locations[0] == "nf_hook_slow"
        assert len(result.top_drop_locations) == 3

    def test_analyze_identifies_causes(self):
        """Test that likely causes are identified."""
        drop_result = PacketDropResult(
            drop_points=[
                DropPoint(location="__netif_receive_skb_core", count=100),
                DropPoint(location="dev_queue_xmit", count=50),
            ],
            total_drops=150,
        )

        result = analyze_packet_drops(drop_result)

        # Should identify causes for these known locations
        assert len(result.likely_causes) > 0

    def test_analyze_drop_rate_capped(self):
        """Test that drop rate is capped at 1.0."""
        drop_result = PacketDropResult(
            drop_points=[
                DropPoint(location="test", count=100000),
            ],
            total_drops=100000,
        )

        result = analyze_packet_drops(drop_result)

        assert result.drop_rate <= 1.0


class TestGenerateDiagnosisReport:
    """Tests for generate_diagnosis_report function."""

    @pytest.fixture
    def sample_request(self):
        """Create sample diagnosis request."""
        return DiagnosisRequest(
            request_id="test-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.75.101",
            dst_host="192.168.75.102",
            src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            dst_vm="be7bb275-715d-5dc1-95c9-3efb045418g2",
        )

    @pytest.fixture
    def sample_measurement(self):
        """Create sample measurement result."""
        return MeasurementResult(
            measurement_id="meas-001",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.SUCCESS,
            metadata=MeasurementMetadata(
                tool_name="test_tool.py",
                host="192.168.75.101",
                duration_sec=30.0,
            ),
        )

    def test_generate_report_minimal(self, sample_request, sample_measurement):
        """Test generating minimal report."""
        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[sample_measurement],
        )

        assert report.request_id == "test-001"
        assert report.source_host == "192.168.75.101"
        assert report.target_host == "192.168.75.102"
        assert report.summary is not None

    def test_generate_report_with_failed_measurements(self, sample_request):
        """Test report generation with failed measurements."""
        failed_measurement = MeasurementResult(
            measurement_id="meas-failed",
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.FAILED,
            error="SSH connection failed",
            metadata=MeasurementMetadata(
                tool_name="test_tool.py",
                host="192.168.75.101",
                duration_sec=0,
            ),
        )

        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[failed_measurement],
        )

        # Should have a finding about measurement failure
        assert len(report.findings) > 0
        assert any("Measurement" in f.title for f in report.findings)

    def test_generate_report_with_latency_analysis(self, sample_request, sample_measurement):
        """Test report generation with latency analysis."""
        from netsherlock.schemas.report import LatencyAnalysis, SegmentAttribution

        latency_analysis = LatencyAnalysis(
            attributions=[
                SegmentAttribution(
                    layer="vm_internal",
                    segments=["virtio_tx"],
                    latency_us=500.0,
                    percentage=0.8,
                    is_anomaly=True,
                ),
            ],
            anomalous_segments=["virtio_tx"],
            total_latency_us=625.0,
            baseline_latency_us=100.0,
            excess_latency_us=525.0,
        )

        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[sample_measurement],
            latency_analysis=latency_analysis,
        )

        assert report.latency_analysis is not None
        # Should have findings about high latency
        assert len(report.findings) > 0

    def test_generate_report_with_drop_analysis(self, sample_request, sample_measurement):
        """Test report generation with drop analysis."""
        from netsherlock.schemas.report import DropAnalysis

        drop_analysis = DropAnalysis(
            total_drops=150,
            drop_rate=0.015,
            top_drop_locations=["nf_hook_slow", "tcp_v4_rcv"],
            likely_causes=["Netfilter/iptables rules dropping packets"],
        )

        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[sample_measurement],
            drop_analysis=drop_analysis,
        )

        assert report.drop_analysis is not None
        # Should have findings about drops
        assert any("Packet Drops" in f.title for f in report.findings)

    def test_generate_report_status_healthy(self, sample_request, sample_measurement):
        """Test report generates healthy status when no issues."""
        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[sample_measurement],
        )

        assert report.summary.status == "healthy"

    def test_generate_report_status_critical(self, sample_request, sample_measurement):
        """Test report generates critical status for severe issues."""
        from netsherlock.schemas.report import LatencyAnalysis, SegmentAttribution

        latency_analysis = LatencyAnalysis(
            attributions=[
                SegmentAttribution(
                    layer="vm_internal",
                    segments=["virtio_tx"],
                    latency_us=10000.0,  # Very high
                    percentage=0.9,
                    is_anomaly=True,
                ),
            ],
            anomalous_segments=["virtio_tx"],
            total_latency_us=11000.0,
            baseline_latency_us=100.0,
            excess_latency_us=10900.0,
        )

        report = generate_diagnosis_report(
            request=sample_request,
            env=None,
            measurements=[sample_measurement],
            latency_analysis=latency_analysis,
        )

        assert report.summary.status == "critical"


class TestIdentifyRootCause:
    """Tests for identify_root_cause function."""

    def test_identify_no_data(self):
        """Test with no analysis data."""
        category, confidence, explanation = identify_root_cause(None, None)

        assert category == RootCauseCategory.UNKNOWN
        assert confidence < 0.5
        assert "Insufficient data" in explanation

    def test_identify_from_latency_anomaly(self):
        """Test identifying root cause from latency anomaly."""
        from netsherlock.schemas.report import LatencyAnalysis, SegmentAttribution

        latency_analysis = LatencyAnalysis(
            attributions=[
                SegmentAttribution(
                    layer="vm_internal",
                    segments=["virtio_tx"],
                    latency_us=500.0,
                    percentage=0.8,
                    is_anomaly=True,
                ),
            ],
            anomalous_segments=["virtio_tx"],
            total_latency_us=625.0,
            baseline_latency_us=100.0,
        )

        category, confidence, explanation = identify_root_cause(latency_analysis, None)

        assert category == RootCauseCategory.VM_INTERNAL
        assert confidence > 0.7
        assert "vm_internal" in explanation

    def test_identify_from_host_internal_latency(self):
        """Test identifying host internal issues."""
        from netsherlock.schemas.report import LatencyAnalysis, SegmentAttribution

        latency_analysis = LatencyAnalysis(
            attributions=[
                SegmentAttribution(
                    layer="host_internal",
                    segments=["ovs_flow"],
                    latency_us=800.0,
                    percentage=0.9,
                    is_anomaly=True,
                ),
            ],
            anomalous_segments=["ovs_flow"],
            total_latency_us=900.0,
            baseline_latency_us=100.0,
        )

        category, confidence, explanation = identify_root_cause(latency_analysis, None)

        assert category == RootCauseCategory.HOST_INTERNAL
        assert "host_internal" in explanation

    def test_identify_from_drops_ovs(self):
        """Test identifying OVS issues from drop analysis."""
        from netsherlock.schemas.report import DropAnalysis

        drop_analysis = DropAnalysis(
            total_drops=100,
            drop_rate=0.01,
            top_drop_locations=["ovs_datapath_flow"],
            likely_causes=["OVS flow table full"],
        )

        category, confidence, explanation = identify_root_cause(None, drop_analysis)

        assert category == RootCauseCategory.HOST_INTERNAL
        assert "OVS" in explanation

    def test_identify_from_drops_netfilter(self):
        """Test identifying netfilter issues from drop analysis."""
        from netsherlock.schemas.report import DropAnalysis

        drop_analysis = DropAnalysis(
            total_drops=50,
            drop_rate=0.005,
            top_drop_locations=["nf_hook_slow"],
            likely_causes=["Netfilter rules"],
        )

        category, confidence, explanation = identify_root_cause(None, drop_analysis)

        assert category == RootCauseCategory.CONFIGURATION
        assert "Netfilter" in explanation

    def test_identify_from_drops_queue(self):
        """Test identifying queue issues from drop analysis."""
        from netsherlock.schemas.report import DropAnalysis

        drop_analysis = DropAnalysis(
            total_drops=200,
            drop_rate=0.02,
            top_drop_locations=["dev_queue_xmit"],
            likely_causes=["TX queue full"],
        )

        category, confidence, explanation = identify_root_cause(None, drop_analysis)

        assert category == RootCauseCategory.RESOURCE_CONTENTION
        assert "Queue" in explanation

    def test_identify_from_drops_unknown_location(self):
        """Test identifying unknown issues from unrecognized drop locations."""
        from netsherlock.schemas.report import DropAnalysis

        drop_analysis = DropAnalysis(
            total_drops=75,
            drop_rate=0.0075,
            top_drop_locations=["unknown_function"],
            likely_causes=[],
        )

        category, confidence, explanation = identify_root_cause(None, drop_analysis)

        assert category == RootCauseCategory.UNKNOWN
        assert "unclear" in explanation.lower()


class TestGetLayerRecommendation:
    """Tests for _get_layer_recommendation function."""

    def test_vm_internal_recommendation(self):
        """Test recommendation for VM internal layer."""
        recommendation = _get_layer_recommendation("vm_internal")

        assert "VM" in recommendation or "virtio" in recommendation

    def test_vhost_processing_recommendation(self):
        """Test recommendation for vhost processing layer."""
        recommendation = _get_layer_recommendation("vhost_processing")

        assert "vhost" in recommendation

    def test_host_internal_recommendation(self):
        """Test recommendation for host internal layer."""
        recommendation = _get_layer_recommendation("host_internal")

        assert "OVS" in recommendation or "datapath" in recommendation

    def test_physical_network_recommendation(self):
        """Test recommendation for physical network layer."""
        recommendation = _get_layer_recommendation("physical_network")

        assert "NIC" in recommendation or "network" in recommendation

    def test_unknown_layer_recommendation(self):
        """Test recommendation for unknown layer."""
        recommendation = _get_layer_recommendation("unknown_layer")

        assert "Investigate" in recommendation
