"""Tests for schema migration and type unification.

These tests verify that:
1. Canonical types are defined in schemas/, not duplicated
2. Types exported from agents/base.py are actually from schemas/
3. All expected types are importable from both locations
4. Backward compatibility is maintained
"""



class TestTypeIdentity:
    """Tests that types from agents/base.py are actually from schemas/."""

    def test_problem_type_is_from_schemas(self):
        """ProblemType should be the same object in both modules."""
        from netsherlock.agents.base import ProblemType as AgentsProblemType
        from netsherlock.schemas.alert import ProblemType as SchemasProblemType

        assert AgentsProblemType is SchemasProblemType

    def test_root_cause_category_is_from_schemas(self):
        """RootCauseCategory should be the same object in both modules."""
        from netsherlock.agents.base import RootCauseCategory as AgentsRootCauseCategory
        from netsherlock.schemas.report import RootCauseCategory as SchemasRootCauseCategory

        assert AgentsRootCauseCategory is SchemasRootCauseCategory

    def test_flow_info_is_from_schemas(self):
        """FlowInfo should be the same object in both modules."""
        from netsherlock.agents.base import FlowInfo as AgentsFlowInfo
        from netsherlock.schemas.environment import FlowInfo as SchemasFlowInfo

        assert AgentsFlowInfo is SchemasFlowInfo

    def test_recommendation_is_from_schemas(self):
        """Recommendation should be the same object in both modules."""
        from netsherlock.agents.base import Recommendation as AgentsRecommendation
        from netsherlock.schemas.report import Recommendation as SchemasRecommendation

        assert AgentsRecommendation is SchemasRecommendation

    def test_root_cause_is_from_schemas(self):
        """RootCause should be the same object in both modules."""
        from netsherlock.agents.base import RootCause as AgentsRootCause
        from netsherlock.schemas.report import RootCause as SchemasRootCause

        assert AgentsRootCause is SchemasRootCause


class TestSchemasExports:
    """Tests that all expected types are exported from schemas/."""

    def test_alert_schemas_exports(self):
        """All alert-related types should be in schemas.alert."""
        from netsherlock.schemas.alert import (
            AlertSeverity,
            ProblemType,
        )

        assert ProblemType is not None
        assert AlertSeverity is not None

    def test_environment_schemas_exports(self):
        """All environment-related types should be in schemas.environment."""
        from netsherlock.schemas.environment import (
            FlowInfo,
            NetworkType,
        )

        assert NetworkType is not None
        assert FlowInfo is not None

    def test_measurement_schemas_exports(self):
        """All measurement-related types should be in schemas.measurement."""
        from netsherlock.schemas.measurement import (
            MeasurementResult,
            MeasurementType,
        )

        assert MeasurementType is not None
        assert MeasurementResult is not None

    def test_report_schemas_exports(self):
        """All report-related types should be in schemas.report."""
        from netsherlock.schemas.report import (
            Recommendation,
            RootCause,
            RootCauseCategory,
        )

        assert RootCauseCategory is not None
        assert RootCause is not None
        assert Recommendation is not None

    def test_config_schemas_exports(self):
        """All config-related types should be in schemas.config."""
        from netsherlock.schemas.config import (
            DiagnosisConfig,
            DiagnosisMode,
        )

        assert DiagnosisMode is not None
        assert DiagnosisConfig is not None


class TestSchemasModuleExports:
    """Tests that schemas/__init__.py exports all types."""

    def test_all_types_importable_from_schemas(self):
        """All types should be importable from the schemas package."""
        from netsherlock.schemas import (
            AlertSeverity,
            CheckpointType,
            DiagnosisConfig,
            # Config
            DiagnosisMode,
            DiagnosisReport,
            DiagnosisRequest,
            # Environment
            FlowInfo,
            LatencyBreakdown,
            # Measurement
            MeasurementResult,
            NetworkPath,
            # Alert
            ProblemType,
            Recommendation,
            RootCause,
            # Report
            RootCauseCategory,
            VMNetworkEnv,
        )

        # Verify types are not None
        assert all([
            ProblemType,
            AlertSeverity,
            DiagnosisRequest,
            DiagnosisMode,
            CheckpointType,
            DiagnosisConfig,
            FlowInfo,
            NetworkPath,
            VMNetworkEnv,
            MeasurementResult,
            LatencyBreakdown,
            RootCauseCategory,
            RootCause,
            Recommendation,
            DiagnosisReport,
        ])


class TestBackwardCompatibility:
    """Tests that backward compatibility is maintained."""

    def test_agents_base_exports_all_legacy_types(self):
        """agents/base.py should export all legacy types."""
        from netsherlock.agents.base import (
            AlertContext,
            VMInfo,
        )
        # DiagnosisResult moved to schemas.result in Phase 0 unification
        from netsherlock.schemas.result import DiagnosisResult

        assert AlertContext is not None
        assert VMInfo is not None
        assert DiagnosisResult is not None

    def test_agents_init_exports_types(self):
        """agents/__init__.py should export types."""
        from netsherlock.agents import (
            ProblemType,
            RootCauseCategory,
        )

        assert ProblemType is not None
        assert RootCauseCategory is not None

    def test_legacy_types_are_dataclasses(self):
        """Legacy types in agents/base.py should be dataclasses."""
        import dataclasses

        from netsherlock.agents.base import (
            AlertContext,
            LatencyHistogram,
            NetworkInfo,
            NodeEnvironment,
            VMInfo,
        )

        assert dataclasses.is_dataclass(AlertContext)
        assert dataclasses.is_dataclass(VMInfo)
        assert dataclasses.is_dataclass(NetworkInfo)
        assert dataclasses.is_dataclass(NodeEnvironment)
        assert dataclasses.is_dataclass(LatencyHistogram)

    def test_schemas_types_are_pydantic_models(self):
        """Types in schemas/ should be Pydantic models."""
        from pydantic import BaseModel

        from netsherlock.schemas import (
            DiagnosisReport,
            FlowInfo,
            Recommendation,
            RootCause,
        )

        assert issubclass(FlowInfo, BaseModel)
        assert issubclass(RootCause, BaseModel)
        assert issubclass(Recommendation, BaseModel)
        assert issubclass(DiagnosisReport, BaseModel)


class TestProblemTypeFunction:
    """Tests for ProblemType.from_alert_name method."""

    def test_from_alert_name_known_alert(self):
        """Should map known alert names."""
        from netsherlock.schemas.alert import ProblemType

        assert ProblemType.from_alert_name("VMNetworkLatency") == ProblemType.VM_NETWORK_LATENCY
        assert ProblemType.from_alert_name("HostNetworkHighLatency") == ProblemType.SYSTEM_NETWORK_LATENCY

    def test_from_alert_name_unknown_alert(self):
        """Should return None for unknown alert names."""
        from netsherlock.schemas.alert import ProblemType

        assert ProblemType.from_alert_name("UnknownAlert") is None
        assert ProblemType.from_alert_name("") is None


class TestNewSchemaTypes:
    """Tests for newly added schema types."""

    def test_flow_info_creation(self):
        """FlowInfo should be creatable with expected fields."""
        from netsherlock.schemas.environment import FlowInfo

        flow = FlowInfo(src_ip="10.0.0.1", dst_ip="10.0.0.2")
        assert flow.src_ip == "10.0.0.1"
        assert flow.dst_ip == "10.0.0.2"
        assert flow.protocol == "icmp"  # default

    def test_root_cause_creation(self):
        """RootCause should be creatable with expected fields."""
        from netsherlock.schemas.report import RootCause, RootCauseCategory

        rc = RootCause(
            category=RootCauseCategory.VM_INTERNAL,
            component="virtio-net",
            confidence=0.85,
        )
        assert rc.category == RootCauseCategory.VM_INTERNAL
        assert rc.confidence == 0.85

    def test_recommendation_creation(self):
        """Recommendation should be creatable with expected fields."""
        from netsherlock.schemas.report import Recommendation

        rec = Recommendation(
            priority=1,
            action="Check VM CPU utilization",
        )
        assert rec.priority == 1
        assert rec.action == "Check VM CPU utilization"
