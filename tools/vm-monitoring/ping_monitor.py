"""Config-driven VM ping monitor with sliding window alerting.

Runs inside a VM, pings configured targets, and triggers netsherlock
diagnosis when anomalies are detected based on sliding window evaluation.

This script is independent from the netsherlock package. It represents
what a customer's monitoring system would do.

Two modes:
  Direct (default): Config-driven monitoring → POST /diagnose on alert
  Prometheus:       Expose metrics for Prometheus scraping

Usage:
    python3 ping_monitor.py --config /etc/ping_monitor/config.yaml
    python3 ping_monitor.py --config config.yaml --mode prometheus --port 9101
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# --- Ping parsing ---

@dataclass
class PingResult:
    """Parsed result from a single ping cycle."""
    target: str
    packets_sent: int
    packets_received: int
    loss_percent: float
    rtt_min_ms: float | None = None
    rtt_avg_ms: float | None = None
    rtt_max_ms: float | None = None


_STATS_RE = re.compile(
    r"(\d+) packets transmitted, (\d+) received.*?(\d+(?:\.\d+)?)% packet loss"
)
_RTT_RE = re.compile(
    r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms"
)


def parse_ping_output(output: str, target: str) -> PingResult:
    """Parse ping command output into structured result."""
    stats_match = _STATS_RE.search(output)
    if not stats_match:
        return PingResult(target=target, packets_sent=0, packets_received=0, loss_percent=100.0)

    sent = int(stats_match.group(1))
    received = int(stats_match.group(2))
    loss = float(stats_match.group(3))

    rtt_match = _RTT_RE.search(output)
    rtt_min = rtt_avg = rtt_max = None
    if rtt_match:
        rtt_min = float(rtt_match.group(1))
        rtt_avg = float(rtt_match.group(2))
        rtt_max = float(rtt_match.group(3))

    return PingResult(
        target=target, packets_sent=sent, packets_received=received,
        loss_percent=loss, rtt_min_ms=rtt_min, rtt_avg_ms=rtt_avg, rtt_max_ms=rtt_max,
    )


def run_ping(target: str, count: int = 5, timeout: int = 10) -> PingResult:
    """Execute ping command and return parsed result."""
    cmd = ["ping", "-c", str(count), "-W", "1", target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return parse_ping_output(result.stdout, target)
    except subprocess.TimeoutExpired:
        return PingResult(target=target, packets_sent=count, packets_received=0, loss_percent=100.0)


# --- Configuration ---

@dataclass
class ThresholdConfig:
    # RTT thresholds increased to prevent false alerts from normal VM latency spikes
    # Normal VM latency: 0.4-1ms, occasional spikes to 5ms+
    rtt_warning_ms: float = 15.0   # Was 5.0 - too low, causing false alerts
    rtt_critical_ms: float = 50.0  # Was 20.0 - increased proportionally
    loss_warning_pct: float = 10.0
    loss_critical_pct: float = 50.0
    cooldown_seconds: int = 3600   # 1 hour - prevent repeat alerts during continuous faults

@dataclass
class TargetConfig:
    dst_vm_name: str
    dst_test_ip: str
    thresholds: ThresholdConfig | None = None  # per-target override

@dataclass
class MonitorEntry:
    src_vm_name: str
    src_test_ip: str
    targets: list[TargetConfig] = field(default_factory=list)

@dataclass
class MonitorConfig:
    netsherlock_url: str = "http://localhost:8080"
    api_key: str = ""
    cycle_pause: int = 1
    count: int = 5
    window_size: int = 3
    trigger_count: int = 2
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    monitors: list[MonitorEntry] = field(default_factory=list)


def load_config(path: str) -> MonitorConfig:
    """Load monitor config from YAML file."""
    import yaml
    with open(path) as f:
        raw = yaml.safe_load(f)

    ns = raw.get("netsherlock", {})
    coll = raw.get("collection", {})
    ev = raw.get("evaluation", {})
    th = raw.get("thresholds", {})

    default_thresholds = ThresholdConfig(
        rtt_warning_ms=th.get("rtt_warning_ms", 5.0),
        rtt_critical_ms=th.get("rtt_critical_ms", 20.0),
        loss_warning_pct=th.get("loss_warning_pct", 10.0),
        loss_critical_pct=th.get("loss_critical_pct", 50.0),
        cooldown_seconds=th.get("cooldown_seconds", 300),
    )

    monitors = []
    for m in raw.get("monitors", []):
        targets = []
        for t in m.get("targets", []):
            t_th = None
            if "thresholds" in t:
                t_raw = t["thresholds"]
                t_th = ThresholdConfig(
                    rtt_warning_ms=t_raw.get("rtt_warning_ms", default_thresholds.rtt_warning_ms),
                    rtt_critical_ms=t_raw.get("rtt_critical_ms", default_thresholds.rtt_critical_ms),
                    loss_warning_pct=t_raw.get("loss_warning_pct", default_thresholds.loss_warning_pct),
                    loss_critical_pct=t_raw.get("loss_critical_pct", default_thresholds.loss_critical_pct),
                    cooldown_seconds=t_raw.get("cooldown_seconds", default_thresholds.cooldown_seconds),
                )
            targets.append(TargetConfig(
                dst_vm_name=t["dst_vm_name"], dst_test_ip=t["dst_test_ip"], thresholds=t_th,
            ))
        monitors.append(MonitorEntry(
            src_vm_name=m["src_vm_name"], src_test_ip=m["src_test_ip"], targets=targets,
        ))

    return MonitorConfig(
        netsherlock_url=ns.get("url", "http://localhost:8080"),
        api_key=ns.get("api_key", ""),
        cycle_pause=coll.get("cycle_pause", 2),
        count=coll.get("count", 5),
        window_size=ev.get("window_size", 3),
        trigger_count=ev.get("trigger_count", 2),
        thresholds=default_thresholds,
        monitors=monitors,
    )


# --- Alert evaluation with sliding window ---

class AlertEvaluator:
    """Sliding window alert evaluator with cooldown."""

    def __init__(
        self,
        window_size: int = 3,
        trigger_count: int = 2,
        rtt_warning_ms: float = 5.0,
        rtt_critical_ms: float = 20.0,
        loss_warning_pct: float = 10.0,
        loss_critical_pct: float = 50.0,
        cooldown_seconds: int = 300,
    ):
        self.window_size = window_size
        self.trigger_count = trigger_count
        self.rtt_warning_ms = rtt_warning_ms
        self.rtt_critical_ms = rtt_critical_ms
        self.loss_warning_pct = loss_warning_pct
        self.loss_critical_pct = loss_critical_pct
        self.cooldown_seconds = cooldown_seconds

        # target → deque of recent PingResults
        self._windows: dict[str, deque] = {}
        # (target, severity) → last fire timestamp
        self._last_fired: dict[tuple[str, str], float] = {}

    def evaluate(self, target: str, result: PingResult) -> dict | None:
        """Evaluate a ping result against the sliding window.

        Returns alert dict if threshold exceeded and cooldown allows, None otherwise.
        """
        # Maintain window
        if target not in self._windows:
            self._windows[target] = deque(maxlen=self.window_size)
        self._windows[target].append(result)

        # Immediate critical: 100% packet loss
        if result.packets_received == 0:
            return self._try_fire(target, "critical",
                f"target unreachable (100% loss)")

        window = list(self._windows[target])

        # RTT evaluation
        rtt_critical_count = sum(
            1 for r in window if r.rtt_avg_ms is not None and r.rtt_avg_ms > self.rtt_critical_ms
        )
        rtt_warning_count = sum(
            1 for r in window if r.rtt_avg_ms is not None and r.rtt_avg_ms > self.rtt_warning_ms
        )

        # Loss evaluation
        loss_critical_count = sum(1 for r in window if r.loss_percent > self.loss_critical_pct)
        loss_warning_count = sum(1 for r in window if r.loss_percent > self.loss_warning_pct)

        # Determine severity (highest first)
        window_dur = len(window) * 10  # approximate window duration
        if rtt_critical_count >= self.trigger_count:
            avg = sum(r.rtt_avg_ms for r in window if r.rtt_avg_ms) / max(rtt_critical_count, 1)
            return self._try_fire(target, "critical",
                f"RTT critical: {rtt_critical_count}/{len(window)} cycles exceeded "
                f"{self.rtt_critical_ms}ms (avg {avg:.1f}ms, window {window_dur}s)")

        if loss_critical_count >= self.trigger_count:
            return self._try_fire(target, "critical",
                f"Loss critical: {loss_critical_count}/{len(window)} cycles exceeded "
                f"{self.loss_critical_pct}% (window {window_dur}s)")

        # Only trigger warning if NO sample exceeds critical threshold.
        # This prevents warning firing during ramp-up to critical level,
        # avoiding duplicate alerts for the same fault event.
        if rtt_warning_count >= self.trigger_count and rtt_critical_count == 0:
            avg = sum(r.rtt_avg_ms for r in window if r.rtt_avg_ms) / max(rtt_warning_count, 1)
            return self._try_fire(target, "warning",
                f"RTT warning: {rtt_warning_count}/{len(window)} cycles exceeded "
                f"{self.rtt_warning_ms}ms (avg {avg:.1f}ms, window {window_dur}s)")

        if loss_warning_count >= self.trigger_count and loss_critical_count == 0:
            return self._try_fire(target, "warning",
                f"Loss warning: {loss_warning_count}/{len(window)} cycles exceeded "
                f"{self.loss_warning_pct}% (window {window_dur}s)")

        return None

    def _try_fire(self, target: str, severity: str, description: str) -> dict | None:
        """Fire alert if cooldown allows. Critical overrides warning cooldown."""
        now = time.time()
        key = (target, severity)

        # Check cooldown (per severity)
        last = self._last_fired.get(key, 0)
        if now - last < self.cooldown_seconds:
            return None

        self._last_fired[key] = now

        # When critical fires, also update warning cooldown to prevent duplicate alerts
        # during the same fault event (warning might fire first as RTT ramps up)
        if severity == "critical":
            self._last_fired[(target, "warning")] = now

        return {"severity": severity, "description": description}


# --- Main loop ---

def run_direct_mode(config: MonitorConfig):
    """Config-driven direct mode: monitor all pairs, trigger on alert."""
    logger.info(f"Direct mode: {len(config.monitors)} monitor entries, "
                f"window={config.window_size}, trigger={config.trigger_count}")

    # Build evaluators per (src, dst) with appropriate thresholds
    evaluators: dict[str, AlertEvaluator] = {}  # keyed by "src→dst"

    for monitor in config.monitors:
        for target in monitor.targets:
            th = target.thresholds or config.thresholds
            pair_key = f"{monitor.src_vm_name}→{target.dst_vm_name}"
            evaluators[pair_key] = AlertEvaluator(
                window_size=config.window_size,
                trigger_count=config.trigger_count,
                rtt_warning_ms=th.rtt_warning_ms,
                rtt_critical_ms=th.rtt_critical_ms,
                loss_warning_pct=th.loss_warning_pct,
                loss_critical_pct=th.loss_critical_pct,
                cooldown_seconds=th.cooldown_seconds,
            )

    while True:
        for monitor in config.monitors:
            for target in monitor.targets:
                result = run_ping(target.dst_test_ip, count=config.count)
                logger.info(f"ping {target.dst_test_ip}: loss={result.loss_percent}% "
                           f"avg={result.rtt_avg_ms}ms")

                pair_key = f"{monitor.src_vm_name}→{target.dst_vm_name}"
                alert = evaluators[pair_key].evaluate(target.dst_test_ip, result)

                if alert:
                    # Build diagnosis request payload
                    payload_dict = {
                        "network_type": "vm",
                        "src_vm_name": monitor.src_vm_name,
                        "dst_vm_name": target.dst_vm_name,
                        "src_test_ip": monitor.src_test_ip,
                        "dst_test_ip": target.dst_test_ip,
                        "severity": alert["severity"],
                        "description": alert["description"],
                    }
                    # Critical severity triggers segment mode (8-point measurement)
                    if alert["severity"] == "critical":
                        payload_dict["options"] = {"segment": True}
                    payload = json.dumps(payload_dict).encode()
                    req = urllib.request.Request(
                        f"{config.netsherlock_url}/diagnose",
                        data=payload,
                        headers={"X-API-Key": config.api_key,
                                 "Content-Type": "application/json"},
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            body = json.loads(resp.read())
                            logger.info(f"[{alert['severity']}] {pair_key}: "
                                       f"{alert['description']} → {body.get('diagnosis_id', '?')}")
                    except Exception as e:
                        logger.error(f"Failed to trigger diagnosis for {pair_key}: {e}")

        time.sleep(config.cycle_pause)


def run_prometheus_mode(config: MonitorConfig, port: int):
    """Prometheus exporter mode: expose metrics for scraping."""
    from prometheus_client import Gauge, start_http_server

    rtt_gauge = Gauge("ping_rtt_ms", "Ping RTT in milliseconds", ["target", "stat"])
    loss_gauge = Gauge("ping_loss_percent", "Ping packet loss", ["target"])
    up_gauge = Gauge("ping_up", "Target reachable", ["target"])

    start_http_server(port)

    all_targets = []
    for monitor in config.monitors:
        for target in monitor.targets:
            all_targets.append(target.dst_test_ip)
    logger.info(f"Prometheus metrics on :{port}, targets: {all_targets}")

    while True:
        for ip in all_targets:
            result = run_ping(ip, count=config.count)
            loss_gauge.labels(target=ip).set(result.loss_percent)
            up_gauge.labels(target=ip).set(1.0 if result.packets_received > 0 else 0.0)
            if result.rtt_min_ms is not None:
                rtt_gauge.labels(target=ip, stat="min").set(result.rtt_min_ms)
                rtt_gauge.labels(target=ip, stat="avg").set(result.rtt_avg_ms)
                rtt_gauge.labels(target=ip, stat="max").set(result.rtt_max_ms)
        time.sleep(config.cycle_pause)


def main():
    parser = argparse.ArgumentParser(
        description="VM ping monitor — config-driven with sliding window alerting"
    )
    parser.add_argument("--config", required=True, help="Path to monitor-config.yaml")
    parser.add_argument("--mode", choices=["direct", "prometheus"], default="direct")
    parser.add_argument("--port", type=int, default=9101, help="Prometheus port")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = load_config(args.config)

    if args.mode == "direct":
        run_direct_mode(config)
    else:
        run_prometheus_mode(config, port=args.port)


if __name__ == "__main__":
    main()
