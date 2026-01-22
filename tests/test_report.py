"""Tests for report schema models.

Tests for DiagnosisReport and related models including markdown generation.
"""


import pytest

from netsherlock.schemas.report import (
    DiagnosisReport,
    DiagnosisSummary,
    DropAnalysis,
    Finding,
    LatencyAnalysis,
    Recommendation,
    RootCause,
    RootCauseCategory,
    SegmentAttribution,
    Severity,
)


class TestSeverityEnum:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test severity enum values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


class TestRootCauseCategoryEnum:
    """Tests for RootCauseCategory enum."""

    def test_root_cause_values(self):
        """Test root cause category values."""
        assert RootCauseCategory.VM_INTERNAL.value == "vm_internal"
        assert RootCauseCategory.HOST_INTERNAL.value == "host_internal"
        assert RootCauseCategory.VHOST_PROCESSING.value == "vhost_processing"
        assert RootCauseCategory.PHYSICAL_NETWORK.value == "physical_network"
        assert RootCauseCategory.CONFIGURATION.value == "configuration"
        assert RootCauseCategory.RESOURCE_CONTENTION.value == "resource_contention"
        assert RootCauseCategory.UNKNOWN.value == "unknown"


class TestSegmentAttribution:
    """Tests for SegmentAttribution model."""

    def test_create_segment_attribution(self):
        """Test creating segment attribution."""
        attr = SegmentAttribution(
            layer="vm_internal",
            segments=["virtio_tx", "virtio_rx"],
            latency_us=150.0,
            percentage=0.5,
            is_anomaly=True,
        )

        assert attr.layer == "vm_internal"
        assert len(attr.segments) == 2
        assert attr.latency_us == 150.0
        assert attr.percentage == 0.5
        assert attr.is_anomaly is True

    def test_default_is_anomaly(self):
        """Test default is_anomaly value."""
        attr = SegmentAttribution(
            layer="vm_internal",
            latency_us=100.0,
            percentage=0.3,
        )

        assert attr.is_anomaly is False


class TestFinding:
    """Tests for Finding model."""

    def test_create_finding(self):
        """Test creating finding."""
        finding = Finding(
            severity=Severity.WARNING,
            category=RootCauseCategory.VM_INTERNAL,
            title="High VM Latency",
            description="VM internal latency is above threshold",
            evidence="virtio_tx: 500us",
            recommendation="Check VM CPU utilization",
        )

        assert finding.severity == Severity.WARNING
        assert finding.category == RootCauseCategory.VM_INTERNAL
        assert finding.title == "High VM Latency"
        assert finding.evidence == "virtio_tx: 500us"

    def test_finding_defaults(self):
        """Test finding default values."""
        finding = Finding(
            severity=Severity.INFO,
            category=RootCauseCategory.UNKNOWN,
            title="Test Finding",
            description="Test description",
        )

        assert finding.evidence == ""
        assert finding.recommendation == ""


class TestLatencyAnalysis:
    """Tests for LatencyAnalysis model."""

    def test_create_latency_analysis(self):
        """Test creating latency analysis."""
        analysis = LatencyAnalysis(
            attributions=[
                SegmentAttribution(
                    layer="vm_internal",
                    segments=["virtio_tx"],
                    latency_us=100.0,
                    percentage=0.5,
                ),
            ],
            anomalous_segments=["virtio_tx"],
            total_latency_us=200.0,
            baseline_latency_us=100.0,
            excess_latency_us=100.0,
        )

        assert len(analysis.attributions) == 1
        assert analysis.total_latency_us == 200.0
        assert analysis.excess_latency_us == 100.0

    def test_latency_analysis_defaults(self):
        """Test latency analysis default values."""
        analysis = LatencyAnalysis()

        assert analysis.attributions == []
        assert analysis.anomalous_segments == []
        assert analysis.total_latency_us == 0.0
        assert analysis.baseline_latency_us is None
        assert analysis.excess_latency_us is None


class TestDropAnalysis:
    """Tests for DropAnalysis model."""

    def test_create_drop_analysis(self):
        """Test creating drop analysis."""
        analysis = DropAnalysis(
            total_drops=150,
            drop_rate=0.015,
            top_drop_locations=["nf_hook_slow", "tcp_v4_rcv"],
            likely_causes=["Netfilter rules"],
        )

        assert analysis.total_drops == 150
        assert analysis.drop_rate == 0.015
        assert len(analysis.top_drop_locations) == 2

    def test_drop_analysis_defaults(self):
        """Test drop analysis default values."""
        analysis = DropAnalysis()

        assert analysis.total_drops == 0
        assert analysis.drop_rate == 0.0
        assert analysis.top_drop_locations == []
        assert analysis.likely_causes == []


class TestRootCause:
    """Tests for RootCause model."""

    def test_create_root_cause(self):
        """Test creating root cause."""
        root_cause = RootCause(
            category=RootCauseCategory.VM_INTERNAL,
            component="virtio driver",
            confidence=0.85,
            evidence=["High latency in virtio_tx"],
            contributing_factors=["High CPU utilization"],
        )

        assert root_cause.category == RootCauseCategory.VM_INTERNAL
        assert root_cause.confidence == 0.85
        assert len(root_cause.evidence) == 1

    def test_root_cause_confidence_validation(self):
        """Test confidence must be between 0 and 1."""
        with pytest.raises(Exception):  # Pydantic validation error
            RootCause(
                category=RootCauseCategory.UNKNOWN,
                component="test",
                confidence=1.5,  # Invalid
            )


class TestRecommendation:
    """Tests for Recommendation model."""

    def test_create_recommendation(self):
        """Test creating recommendation."""
        rec = Recommendation(
            priority=1,
            action="Increase virtio queue size",
            command="virsh edit $vm",
            metric="virtio_tx latency",
            rationale="Queue overflow detected",
        )

        assert rec.priority == 1
        assert rec.action == "Increase virtio queue size"
        assert rec.command == "virsh edit $vm"

    def test_recommendation_defaults(self):
        """Test recommendation default values."""
        rec = Recommendation(
            priority=2,
            action="Test action",
        )

        assert rec.command == ""
        assert rec.metric == ""
        assert rec.rationale == ""


class TestDiagnosisSummary:
    """Tests for DiagnosisSummary model."""

    def test_create_summary(self):
        """Test creating summary."""
        summary = DiagnosisSummary(
            status="critical",
            primary_issue="High VM latency",
            root_cause=RootCauseCategory.VM_INTERNAL,
            confidence=0.9,
        )

        assert summary.status == "critical"
        assert summary.primary_issue == "High VM latency"
        assert summary.confidence == 0.9

    def test_summary_defaults(self):
        """Test summary default values."""
        summary = DiagnosisSummary(status="healthy")

        assert summary.primary_issue is None
        assert summary.root_cause == RootCauseCategory.UNKNOWN
        assert summary.confidence == 0.0


class TestDiagnosisReport:
    """Tests for DiagnosisReport model."""

    @pytest.fixture
    def minimal_report(self):
        """Create minimal report."""
        return DiagnosisReport(
            report_id="test-001",
            request_id="req-001",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="healthy"),
        )

    def test_create_minimal_report(self, minimal_report):
        """Test creating minimal report."""
        assert minimal_report.report_id == "test-001"
        assert minimal_report.source_host == "192.168.75.101"
        assert minimal_report.summary.status == "healthy"

    def test_report_defaults(self, minimal_report):
        """Test report default values."""
        assert minimal_report.target_host is None
        assert minimal_report.vm_id is None
        assert minimal_report.latency_analysis is None
        assert minimal_report.drop_analysis is None
        assert minimal_report.findings == []
        assert minimal_report.recommendations == []

    def test_report_with_all_fields(self):
        """Test creating report with all fields."""
        report = DiagnosisReport(
            report_id="test-002",
            request_id="req-002",
            source_host="192.168.75.101",
            target_host="192.168.75.102",
            vm_id="ae6aa164-604c-4cb0-84b8-2dea034307f1",
            diagnosis_type="latency",
            summary=DiagnosisSummary(
                status="degraded",
                primary_issue="High latency",
                confidence=0.8,
            ),
            latency_analysis=LatencyAnalysis(
                attributions=[
                    SegmentAttribution(
                        layer="vm_internal",
                        latency_us=200.0,
                        percentage=0.6,
                        is_anomaly=True,
                    ),
                ],
                total_latency_us=330.0,
            ),
            findings=[
                Finding(
                    severity=Severity.WARNING,
                    category=RootCauseCategory.VM_INTERNAL,
                    title="High VM Latency",
                    description="VM internal latency is elevated",
                ),
            ],
            recommendations=["Check VM CPU", "Increase queue size"],
            measurement_duration_sec=30.0,
            total_analysis_time_sec=1.5,
        )

        assert report.target_host == "192.168.75.102"
        assert report.vm_id is not None
        assert report.latency_analysis is not None
        assert len(report.findings) == 1
        assert len(report.recommendations) == 2


class TestDiagnosisReportMarkdown:
    """Tests for DiagnosisReport.to_markdown method."""

    def test_markdown_minimal(self):
        """Test markdown generation for minimal report."""
        report = DiagnosisReport(
            report_id="test-001",
            request_id="req-001",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="healthy"),
        )

        markdown = report.to_markdown()

        assert "# Network Diagnosis Report" in markdown
        assert "test-001" in markdown
        assert "192.168.75.101" in markdown
        assert "HEALTHY" in markdown

    def test_markdown_with_vm(self):
        """Test markdown includes VM info."""
        report = DiagnosisReport(
            report_id="test-002",
            request_id="req-002",
            source_host="192.168.75.101",
            vm_id="ae6aa164",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="healthy"),
        )

        markdown = report.to_markdown()

        assert "ae6aa164" in markdown

    def test_markdown_with_target(self):
        """Test markdown includes target host."""
        report = DiagnosisReport(
            report_id="test-003",
            request_id="req-003",
            source_host="192.168.75.101",
            target_host="192.168.75.102",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="healthy"),
        )

        markdown = report.to_markdown()

        assert "192.168.75.102" in markdown

    def test_markdown_with_latency_analysis(self):
        """Test markdown includes latency analysis section."""
        report = DiagnosisReport(
            report_id="test-004",
            request_id="req-004",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="degraded"),
            latency_analysis=LatencyAnalysis(
                attributions=[
                    SegmentAttribution(
                        layer="vm_internal",
                        latency_us=200.0,
                        percentage=0.6,
                        is_anomaly=True,
                    ),
                    SegmentAttribution(
                        layer="host_internal",
                        latency_us=130.0,
                        percentage=0.4,
                        is_anomaly=False,
                    ),
                ],
                total_latency_us=330.0,
            ),
        )

        markdown = report.to_markdown()

        assert "## Latency Analysis" in markdown
        assert "330.0" in markdown
        assert "vm_internal" in markdown
        assert "60.0%" in markdown  # 0.6 as percentage

    def test_markdown_with_drop_analysis(self):
        """Test markdown includes drop analysis section."""
        report = DiagnosisReport(
            report_id="test-005",
            request_id="req-005",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="critical"),
            drop_analysis=DropAnalysis(
                total_drops=150,
                drop_rate=0.015,
                top_drop_locations=["nf_hook_slow"],
            ),
        )

        markdown = report.to_markdown()

        assert "## Packet Drop Analysis" in markdown
        assert "150" in markdown
        assert "1.50%" in markdown  # drop rate

    def test_markdown_with_findings(self):
        """Test markdown includes findings section."""
        report = DiagnosisReport(
            report_id="test-006",
            request_id="req-006",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="degraded"),
            findings=[
                Finding(
                    severity=Severity.CRITICAL,
                    category=RootCauseCategory.VM_INTERNAL,
                    title="Critical VM Latency",
                    description="VM internal latency is critical",
                    evidence="virtio_tx: 2000us",
                    recommendation="Restart VM",
                ),
                Finding(
                    severity=Severity.WARNING,
                    category=RootCauseCategory.HOST_INTERNAL,
                    title="OVS Congestion",
                    description="OVS flow table is large",
                ),
                Finding(
                    severity=Severity.INFO,
                    category=RootCauseCategory.UNKNOWN,
                    title="Info Finding",
                    description="Just information",
                ),
            ],
        )

        markdown = report.to_markdown()

        assert "## Findings" in markdown
        assert "Critical VM Latency" in markdown
        assert "virtio_tx: 2000us" in markdown
        assert "Restart VM" in markdown

    def test_markdown_with_recommendations(self):
        """Test markdown includes recommendations section."""
        report = DiagnosisReport(
            report_id="test-007",
            request_id="req-007",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="degraded"),
            recommendations=[
                "Check VM CPU utilization",
                "Increase virtio queue size",
                "Review OVS flow rules",
            ],
        )

        markdown = report.to_markdown()

        assert "## Recommendations" in markdown
        assert "1. Check VM CPU utilization" in markdown
        assert "2. Increase virtio queue size" in markdown
        assert "3. Review OVS flow rules" in markdown

    def test_markdown_no_drop_section_when_zero_drops(self):
        """Test markdown excludes drop section when no drops."""
        report = DiagnosisReport(
            report_id="test-008",
            request_id="req-008",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="healthy"),
            drop_analysis=DropAnalysis(
                total_drops=0,
                drop_rate=0.0,
            ),
        )

        markdown = report.to_markdown()

        assert "## Packet Drop Analysis" not in markdown

    def test_markdown_anomaly_flag(self):
        """Test markdown shows anomaly flag."""
        report = DiagnosisReport(
            report_id="test-009",
            request_id="req-009",
            source_host="192.168.75.101",
            diagnosis_type="latency",
            summary=DiagnosisSummary(status="degraded"),
            latency_analysis=LatencyAnalysis(
                attributions=[
                    SegmentAttribution(
                        layer="vm_internal",
                        latency_us=500.0,
                        percentage=0.9,
                        is_anomaly=True,
                    ),
                ],
                total_latency_us=555.0,
            ),
        )

        markdown = report.to_markdown()

        # Anomaly flag should be present (warning emoji)
        assert "vm_internal" in markdown
