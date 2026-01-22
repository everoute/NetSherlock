"""Tests for Analysis result schemas."""


import pytest

from netsherlock.schemas.analysis import (
    AnalysisResult,
    LatencyBreakdown,
    LayerData,
    LayerType,
    ProbableCause,
    Recommendation,
    SegmentData,
)


class TestSegmentData:
    """Tests for SegmentData."""

    def test_create_segment(self):
        """Create segment data."""
        segment = SegmentData(
            name="A",
            value_us=150.5,
            source="kernel_icmp_rtt.py",
            description="Application to virtio-net",
        )
        assert segment.name == "A"
        assert segment.value_us == 150.5
        assert segment.source == "kernel_icmp_rtt.py"

    def test_value_ms_conversion(self):
        """Convert microseconds to milliseconds."""
        segment = SegmentData(name="A", value_us=1500.0)
        assert segment.value_ms == 1.5


class TestLayerData:
    """Tests for LayerData."""

    def test_create_layer_data(self):
        """Create layer data."""
        layer = LayerData(
            layer=LayerType.VM_KERNEL,
            total_us=500.0,
            percentage=25.0,
            segments=["A", "F", "G", "H", "M"],
        )
        assert layer.layer == LayerType.VM_KERNEL
        assert layer.total_us == 500.0
        assert layer.percentage == 25.0

    def test_total_ms_conversion(self):
        """Convert total to milliseconds."""
        layer = LayerData(layer=LayerType.HOST_OVS, total_us=2500.0)
        assert layer.total_ms == 2.5


class TestLatencyBreakdown:
    """Tests for LatencyBreakdown."""

    @pytest.fixture
    def sample_breakdown(self):
        """Create sample breakdown."""
        breakdown = LatencyBreakdown(
            total_rtt_us=2000.0,
            segments={
                "A": SegmentData(name="A", value_us=100.0),
                "B": SegmentData(name="B", value_us=200.0),
                "C_J": SegmentData(name="C_J", value_us=300.0),
                "D": SegmentData(name="D", value_us=150.0),
                "E": SegmentData(name="E", value_us=250.0),
                "F": SegmentData(name="F", value_us=120.0),
                "G": SegmentData(name="G", value_us=80.0),
                "H": SegmentData(name="H", value_us=100.0),
                "I": SegmentData(name="I", value_us=180.0),
                "K": SegmentData(name="K", value_us=170.0),
                "L": SegmentData(name="L", value_us=200.0),
                "M": SegmentData(name="M", value_us=150.0),
            },
        )
        return breakdown

    def test_create_breakdown(self, sample_breakdown):
        """Create latency breakdown."""
        assert sample_breakdown.total_rtt_us == 2000.0
        assert len(sample_breakdown.segments) == 12

    def test_total_rtt_ms(self, sample_breakdown):
        """Get total RTT in milliseconds."""
        assert sample_breakdown.total_rtt_ms == 2.0

    def test_get_segment(self, sample_breakdown):
        """Get segment by name."""
        segment = sample_breakdown.get_segment("A")
        assert segment is not None
        assert segment.value_us == 100.0

        assert sample_breakdown.get_segment("nonexistent") is None

    def test_calculate_layer_attribution(self, sample_breakdown):
        """Calculate layer attribution from segments."""
        sample_breakdown.calculate_layer_attribution()

        assert len(sample_breakdown.layer_attribution) == 5

        # Check VM kernel layer
        vm_layer = sample_breakdown.get_layer(LayerType.VM_KERNEL)
        assert vm_layer is not None
        # A + F + G + H + M = 100 + 120 + 80 + 100 + 150 = 550
        assert vm_layer.total_us == 550.0

    def test_get_primary_contributor(self, sample_breakdown):
        """Get primary contributor layer."""
        sample_breakdown.calculate_layer_attribution()

        primary = sample_breakdown.get_primary_contributor()
        assert primary is not None

    def test_to_dict(self, sample_breakdown):
        """Convert to dictionary."""
        sample_breakdown.calculate_layer_attribution()
        d = sample_breakdown.to_dict()

        assert "total_rtt_us" in d
        assert "total_rtt_ms" in d
        assert "segments" in d
        assert "layer_attribution" in d
        assert "primary_contributor" in d

    def test_empty_breakdown(self):
        """Empty breakdown."""
        breakdown = LatencyBreakdown(total_rtt_us=0.0)
        assert breakdown.get_primary_contributor() is None


class TestProbableCause:
    """Tests for ProbableCause."""

    def test_create_probable_cause(self):
        """Create probable cause."""
        cause = ProbableCause(
            cause="vhost CPU overload",
            confidence=0.85,
            evidence=["high vhost-net latency", "CPU bound on core 2"],
            layer=LayerType.VIRT_TX,
        )
        assert cause.cause == "vhost CPU overload"
        assert cause.confidence == 0.85
        assert len(cause.evidence) == 2
        assert cause.layer == LayerType.VIRT_TX


class TestRecommendation:
    """Tests for Recommendation."""

    def test_create_recommendation(self):
        """Create recommendation."""
        rec = Recommendation(
            action="Pin vhost threads to dedicated cores",
            priority="high",
            rationale="Reduce context switching overhead",
        )
        assert rec.action == "Pin vhost threads to dedicated cores"
        assert rec.priority == "high"


class TestAnalysisResult:
    """Tests for AnalysisResult."""

    @pytest.fixture
    def sample_breakdown(self):
        """Create sample breakdown."""
        return LatencyBreakdown(
            total_rtt_us=2000.0,
            segments={
                "A": SegmentData(name="A", value_us=100.0),
                "B": SegmentData(name="B", value_us=200.0),
            },
        )

    def test_create_analysis_result(self, sample_breakdown):
        """Create analysis result."""
        result = AnalysisResult(
            breakdown=sample_breakdown,
            primary_contributor=LayerType.VIRT_TX,
            confidence=0.85,
            reasoning="Based on segment analysis...",
        )
        assert result.breakdown.total_rtt_us == 2000.0
        assert result.primary_contributor == LayerType.VIRT_TX
        assert result.confidence == 0.85

    def test_from_breakdown(self, sample_breakdown):
        """Create from breakdown (Phase 1 only)."""
        sample_breakdown.calculate_layer_attribution()
        result = AnalysisResult.from_breakdown(sample_breakdown)

        assert result.breakdown == sample_breakdown
        assert result.primary_contributor is not None

    def test_add_probable_cause(self, sample_breakdown):
        """Add probable cause."""
        result = AnalysisResult(breakdown=sample_breakdown)

        result.add_probable_cause(
            cause="OVS flow miss",
            confidence=0.75,
            evidence=["High upcall rate"],
            layer=LayerType.HOST_OVS,
        )

        assert len(result.probable_causes) == 1
        assert result.probable_causes[0].cause == "OVS flow miss"

    def test_add_recommendation(self, sample_breakdown):
        """Add recommendation."""
        result = AnalysisResult(breakdown=sample_breakdown)

        result.add_recommendation(
            action="Review OVS flow rules",
            priority="medium",
            rationale="Many flows hitting slow path",
        )

        assert len(result.recommendations) == 1
        assert result.recommendations[0].action == "Review OVS flow rules"

    def test_to_dict(self, sample_breakdown):
        """Convert to dictionary."""
        result = AnalysisResult(
            breakdown=sample_breakdown,
            primary_contributor=LayerType.VM_KERNEL,
            confidence=0.8,
        )
        result.add_probable_cause("Test cause", confidence=0.7)
        result.add_recommendation("Test action", priority="high")

        d = result.to_dict()

        assert "breakdown" in d
        assert "primary_contributor" in d
        assert "probable_causes" in d
        assert "recommendations" in d
        assert "confidence" in d
        assert d["primary_contributor"] == "vm_kernel"

    def test_summary(self, sample_breakdown):
        """Generate summary."""
        result = AnalysisResult(
            breakdown=sample_breakdown,
            primary_contributor=LayerType.HOST_OVS,
        )
        result.add_probable_cause("Test cause", confidence=0.8)
        result.add_recommendation("Test action", priority="high")

        summary = result.summary()

        assert "Total RTT" in summary
        assert "Primary Contributor" in summary
        assert "Probable Causes" in summary
        assert "Recommendations" in summary


class TestLayerType:
    """Tests for LayerType enum."""

    def test_all_layer_types(self):
        """All layer types exist."""
        assert LayerType.VM_KERNEL.value == "vm_kernel"
        assert LayerType.HOST_OVS.value == "host_ovs"
        assert LayerType.PHYSICAL_NETWORK.value == "physical_network"
        assert LayerType.VIRT_RX.value == "virt_rx"
        assert LayerType.VIRT_TX.value == "virt_tx"
