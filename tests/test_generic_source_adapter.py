"""Tests for Generic source adapter (VM name-based /diagnose requests)."""
import pytest
from unittest.mock import patch, MagicMock

from netsherlock.api.webhook import DiagnosticRequest, _build_diagnosis_request


class TestDiagnosticRequestVmNameFields:

    def test_vm_name_request_valid(self):
        """src_vm_name/dst_vm_name without src_host should be valid."""
        req = DiagnosticRequest(
            network_type="vm",
            src_vm_name="web-server-01",
            dst_vm_name="db-server-01",
            src_test_ip="192.168.77.83",
            dst_test_ip="192.168.76.244",
        )
        assert req.src_vm_name == "web-server-01"
        assert req.src_host is None

    def test_explicit_fields_still_work(self):
        """Traditional request with explicit fields still works."""
        req = DiagnosticRequest(
            network_type="vm",
            src_host="192.168.70.31",
            src_vm="uuid-sender",
            dst_host="192.168.70.32",
            dst_vm="uuid-receiver",
        )
        assert req.src_host == "192.168.70.31"

    def test_neither_src_host_nor_src_vm_name_fails(self):
        """Must provide either src_host or src_vm_name."""
        with pytest.raises(ValueError, match="src_host.*src_vm_name"):
            DiagnosticRequest(network_type="vm")


class TestBuildDiagnosisRequestWithVmName:

    def test_vm_name_resolution(self):
        mock_inventory = MagicMock()
        mock_inventory.resolve_vm_pair.return_value = {
            "src_host": "192.168.70.31",
            "src_vm": "uuid-sender",
            "dst_host": "192.168.70.32",
            "dst_vm": "uuid-receiver",
        }

        raw_data = {
            "network_type": "vm",
            "src_vm_name": "web-server-01",
            "dst_vm_name": "db-server-01",
            "src_test_ip": "192.168.77.83",
            "dst_test_ip": "192.168.76.244",
            "description": "ping RTT 15ms",
        }

        with patch(
            "netsherlock.api.webhook._get_global_inventory",
            return_value=mock_inventory,
        ):
            request = _build_diagnosis_request("manual", "manual-001", raw_data)

        assert request.src_host == "192.168.70.31"
        assert request.src_vm == "uuid-sender"
        assert request.dst_host == "192.168.70.32"
        assert request.dst_vm == "uuid-receiver"
        mock_inventory.resolve_vm_pair.assert_called_once_with(
            "web-server-01", "db-server-01"
        )

    def test_explicit_fields_skip_resolution(self):
        """If src_host/src_vm provided, don't resolve."""
        raw_data = {
            "network_type": "vm",
            "src_host": "192.168.70.31",
            "src_vm": "explicit-uuid",
        }

        request = _build_diagnosis_request("manual", "manual-002", raw_data)
        assert request.src_vm == "explicit-uuid"
