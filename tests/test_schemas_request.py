"""Tests for unified DiagnosisRequest model.

Tests creation, validation rules, and serialization of the
unified DiagnosisRequest in schemas/request.py.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.request import DiagnosisRequest


class TestDiagnosisRequestCreation:
    """DiagnosisRequest creation and default values."""

    def test_minimal_vm_request(self):
        """Minimal VM request requires request_type, network_type=vm, src_host, src_vm."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="uuid-1234",
        )
        assert req.request_type == "latency"
        assert req.network_type == "vm"
        assert req.src_host == "192.168.1.10"
        assert req.src_vm == "uuid-1234"

    def test_minimal_system_request(self):
        """Minimal system request needs request_type, network_type=system, src_host."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.network_type == "system"
        assert req.src_vm is None

    def test_request_id_auto_generated(self):
        """Unspecified request_id auto-generates diag-* format."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.request_id.startswith("diag-")
        assert len(req.request_id) == 21  # "diag-" + 16 hex chars

    def test_request_id_custom(self):
        """Custom request_id is preserved."""
        req = DiagnosisRequest(
            request_id="my-custom-id",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.request_id == "my-custom-id"

    def test_default_source_is_cli(self):
        """Default source is CLI."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.source == DiagnosisRequestSource.CLI

    def test_default_mode_is_none(self):
        """Default mode is None (determined by config)."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.mode is None

    def test_default_options_empty_dict(self):
        """Default options is empty dict."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.options == {}


class TestDiagnosisRequestValidation:
    """DiagnosisRequest model_post_init validation rules."""

    def test_vm_network_without_src_vm_raises(self):
        """network_type=vm without src_vm raises ValueError."""
        with pytest.raises(ValueError, match="--src-vm is required"):
            DiagnosisRequest(
                request_type="latency",
                network_type="vm",
                src_host="192.168.1.10",
            )

    def test_vm_network_dst_host_without_dst_vm_raises(self):
        """network_type=vm with dst_host but no dst_vm raises ValueError."""
        with pytest.raises(ValueError, match="--dst-vm is required"):
            DiagnosisRequest(
                request_type="latency",
                network_type="vm",
                src_host="192.168.1.10",
                src_vm="uuid-1234",
                dst_host="192.168.1.20",
            )

    def test_vm_network_dst_vm_without_dst_host_raises(self):
        """dst_vm without dst_host raises ValueError."""
        with pytest.raises(ValueError, match="--dst-host is required"):
            DiagnosisRequest(
                request_type="latency",
                network_type="vm",
                src_host="192.168.1.10",
                src_vm="uuid-1234",
                dst_vm="uuid-5678",
            )

    def test_system_network_no_src_vm_ok(self):
        """network_type=system without src_vm does not raise."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
        )
        assert req.src_vm is None

    def test_cross_node_vm_request_valid(self):
        """Complete cross-node VM request passes validation."""
        req = DiagnosisRequest(
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="uuid-1234",
            dst_host="192.168.1.20",
            dst_vm="uuid-5678",
        )
        assert req.dst_host == "192.168.1.20"
        assert req.dst_vm == "uuid-5678"

    def test_invalid_request_type_rejected(self):
        """Invalid request_type raises ValidationError."""
        with pytest.raises(ValidationError):
            DiagnosisRequest(
                request_type="bandwidth",
                network_type="system",
                src_host="192.168.1.10",
            )

    def test_invalid_network_type_rejected(self):
        """Invalid network_type raises ValidationError."""
        with pytest.raises(ValidationError):
            DiagnosisRequest(
                request_type="latency",
                network_type="cloud",
                src_host="192.168.1.10",
            )


class TestDiagnosisRequestSerialization:
    """DiagnosisRequest serialization/deserialization."""

    def test_model_dump_roundtrip(self):
        """dict -> DiagnosisRequest -> dict roundtrip is consistent."""
        req = DiagnosisRequest(
            request_id="round-trip",
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="uuid-1234",
            source=DiagnosisRequestSource.WEBHOOK,
            mode=DiagnosisMode.AUTONOMOUS,
        )
        data = req.model_dump()
        restored = DiagnosisRequest(**data)
        assert restored.request_id == req.request_id
        assert restored.source == req.source
        assert restored.mode == req.mode

    def test_json_serialization(self):
        """model_dump_json() and model_validate_json() roundtrip."""
        req = DiagnosisRequest(
            request_id="json-test",
            request_type="packet_drop",
            network_type="system",
            src_host="192.168.1.10",
        )
        json_str = req.model_dump_json()
        restored = DiagnosisRequest.model_validate_json(json_str)
        assert restored.request_id == "json-test"
        assert restored.request_type == "packet_drop"
