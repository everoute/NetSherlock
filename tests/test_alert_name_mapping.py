"""Tests for Prometheus source adapter alert name mapping."""
import pytest
from netsherlock.api.webhook import _map_alert_to_type


class TestAlertNameMapping:

    @pytest.mark.parametrize("alertname,expected", [
        ("VMNetworkLatency", "latency"),
        ("HostNetworkLatency", "latency"),
        ("VMPacketDrop", "packet_drop"),
        ("HostPacketDrop", "packet_drop"),
        ("VMConnectivity", "connectivity"),
        ("VMNetworkLatencyHigh", "latency"),
        ("VMNetworkLatencyCritical", "latency"),
        ("VMNetworkPacketLoss", "packet_drop"),
        ("VMNetworkDown", "connectivity"),
        ("UnknownAlert", "latency"),
    ])
    def test_mapping(self, alertname, expected):
        assert _map_alert_to_type(alertname) == expected
