"""Tests for standalone VM ping monitor."""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "vm-monitoring"))

from ping_monitor import (
    PingResult, parse_ping_output, AlertEvaluator, MonitorConfig,
    load_config,
)


class TestParsePingOutput:

    def test_parse_successful_ping(self):
        output = """\
PING 192.168.76.244 (192.168.76.244) 56(84) bytes of data.
64 bytes from 192.168.76.244: icmp_seq=1 ttl=64 time=0.523 ms
64 bytes from 192.168.76.244: icmp_seq=2 ttl=64 time=0.411 ms
64 bytes from 192.168.76.244: icmp_seq=3 ttl=64 time=0.387 ms

--- 192.168.76.244 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
rtt min/avg/max/mdev = 0.387/0.440/0.523/0.059 ms
"""
        result = parse_ping_output(output, "192.168.76.244")
        assert result.target == "192.168.76.244"
        assert result.packets_sent == 3
        assert result.packets_received == 3
        assert result.loss_percent == 0.0
        assert result.rtt_avg_ms == pytest.approx(0.440)

    def test_parse_total_loss(self):
        output = """\
PING 192.168.76.244 (192.168.76.244) 56(84) bytes of data.

--- 192.168.76.244 ping statistics ---
5 packets transmitted, 0 received, 100% packet loss, time 4008ms
"""
        result = parse_ping_output(output, "192.168.76.244")
        assert result.loss_percent == 100.0
        assert result.rtt_avg_ms is None

    def test_parse_partial_loss(self):
        output = """\
PING 192.168.76.244 (192.168.76.244) 56(84) bytes of data.
64 bytes from 192.168.76.244: icmp_seq=1 ttl=64 time=0.523 ms

--- 192.168.76.244 ping statistics ---
5 packets transmitted, 1 received, 80% packet loss, time 4006ms
rtt min/avg/max/mdev = 0.523/0.523/0.523/0.000 ms
"""
        result = parse_ping_output(output, "192.168.76.244")
        assert result.loss_percent == 80.0
        assert result.packets_received == 1


class TestAlertEvaluator:
    """Test sliding window alert evaluation."""

    def _make_result(self, target="192.168.76.244", avg_ms=1.0, loss=0.0, received=5):
        return PingResult(
            target=target, packets_sent=5, packets_received=received,
            loss_percent=loss, rtt_avg_ms=avg_ms if received > 0 else None,
        )

    def test_no_alert_below_threshold(self):
        evaluator = AlertEvaluator(
            window_size=3, trigger_count=2,
            rtt_warning_ms=5.0, rtt_critical_ms=20.0,
            loss_warning_pct=10.0, loss_critical_pct=50.0,
            cooldown_seconds=300,
        )
        # 3 normal cycles
        for _ in range(3):
            alert = evaluator.evaluate("192.168.76.244", self._make_result(avg_ms=1.0))
        assert alert is None

    def test_warning_after_trigger_count(self):
        evaluator = AlertEvaluator(
            window_size=3, trigger_count=2,
            rtt_warning_ms=5.0, rtt_critical_ms=20.0,
            loss_warning_pct=10.0, loss_critical_pct=50.0,
            cooldown_seconds=0,  # no cooldown for test
        )
        evaluator.evaluate("t", self._make_result(avg_ms=1.0))
        evaluator.evaluate("t", self._make_result(avg_ms=6.0))
        alert = evaluator.evaluate("t", self._make_result(avg_ms=7.0))
        assert alert is not None
        assert alert["severity"] == "warning"

    def test_critical_immediate_on_total_loss(self):
        evaluator = AlertEvaluator(
            window_size=3, trigger_count=2,
            rtt_warning_ms=5.0, rtt_critical_ms=20.0,
            loss_warning_pct=10.0, loss_critical_pct=50.0,
            cooldown_seconds=0,
        )
        alert = evaluator.evaluate(
            "t", self._make_result(avg_ms=None, loss=100.0, received=0)
        )
        assert alert is not None
        assert alert["severity"] == "critical"

    def test_cooldown_suppresses_duplicate(self):
        evaluator = AlertEvaluator(
            window_size=3, trigger_count=2,
            rtt_warning_ms=5.0, rtt_critical_ms=20.0,
            loss_warning_pct=10.0, loss_critical_pct=50.0,
            cooldown_seconds=300,
        )
        evaluator.evaluate("t", self._make_result(avg_ms=6.0))
        alert1 = evaluator.evaluate("t", self._make_result(avg_ms=7.0))
        assert alert1 is not None  # first fire
        alert2 = evaluator.evaluate("t", self._make_result(avg_ms=8.0))
        assert alert2 is None  # suppressed by cooldown

    def test_critical_overrides_warning_cooldown(self):
        evaluator = AlertEvaluator(
            window_size=3, trigger_count=2,
            rtt_warning_ms=5.0, rtt_critical_ms=20.0,
            loss_warning_pct=10.0, loss_critical_pct=50.0,
            cooldown_seconds=300,
        )
        evaluator.evaluate("t", self._make_result(avg_ms=6.0))
        alert1 = evaluator.evaluate("t", self._make_result(avg_ms=7.0))
        assert alert1["severity"] == "warning"
        # Critical should still fire despite warning cooldown
        evaluator.evaluate("t", self._make_result(avg_ms=25.0))
        alert2 = evaluator.evaluate("t", self._make_result(avg_ms=30.0))
        assert alert2 is not None
        assert alert2["severity"] == "critical"
