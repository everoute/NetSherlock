#!/usr/bin/env python3
"""System Network Packet Drop & Latency Measurement - Main Entry Point (v2).

Deploys system_*_path_tracer.py to sender and receiver hosts for
packet drop detection and internal latency measurement.

v2 additions:
- Multi-protocol support: ICMP (MVP), TCP/UDP (reserved)
- Direction mode for ICMP: rx (local responds), tx (local initiates)
- Focus mode: drop (丢包定界) vs latency (延迟定界)
- Output mode: verbose (per-packet) vs stats (periodic histograms)

The tool traces 4 stages on each host:
  ICMP RX: [0] ReqRX@phy → [1] ReqRcv@stack → [2] RepSnd@stack → [3] RepTX@phy
  ICMP TX: [0] ReqSnd@stack → [1] ReqTX@phy → [2] RepRX@phy → [3] RepRcv@stack

Workflow:
1. Validate SSH connectivity
2. Start background traffic (if --generate-traffic)
3. Deploy system_*_path_tracer.py to both hosts
4. Start measurement (receiver first)
5. Wait for duration
6. Stop tools and collect logs
7. Parse logs and output JSON
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_script_dir() -> Path:
    return Path(__file__).parent.resolve()


def get_tool_name(protocol: str) -> str:
    """Get the BPF tool name for the given protocol."""
    tools = {
        'icmp': 'system_icmp_path_tracer.py',
        'tcp': 'system_tcp_path_tracer.py',
        'udp': 'system_udp_path_tracer.py'
    }
    return tools[protocol]


def run_script(script_name: str, env: dict, description: str, quiet: bool = False):
    script_path = get_script_dir() / script_name
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)
    if not quiet:
        print(f"\n{'='*60}")
        print(f"[Step] {description}")
        print(f"{'='*60}")
    return subprocess.run(["bash", str(script_path)], env={**os.environ, **env}, capture_output=False)


def parse_args():
    parser = argparse.ArgumentParser(
        description="System Network Packet Drop & Latency Measurement (v2)"
    )

    # L2 environment
    parser.add_argument("--sender-host-ssh", required=True)
    parser.add_argument("--sender-ip", required=True, help="Sender host IP (ping initiator)")
    parser.add_argument("--sender-phy-if", required=True, help="Sender physical NIC (e.g. enp24s0f0np0)")
    parser.add_argument("--receiver-host-ssh", required=True)
    parser.add_argument("--receiver-ip", required=True, help="Receiver host IP (ping target)")
    parser.add_argument("--receiver-phy-if", required=True, help="Receiver physical NIC")
    parser.add_argument("--local-tools-path", required=True)

    # v2: Protocol and mode parameters
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp',
                        help='Protocol to trace (default: icmp). Note: TCP/UDP reserved for future.')
    parser.add_argument("--direction", choices=['rx', 'tx'], default='rx',
                        help='Direction for ICMP: rx=local responds (default), tx=local initiates')
    parser.add_argument("--focus", choices=['drop', 'latency'], default='drop',
                        help='Measurement focus: drop=drop detection (default), latency=latency breakdown')
    parser.add_argument("--output-mode", choices=['verbose', 'stats'], default='verbose',
                        help='Output mode: verbose=per-packet (default), stats=periodic histograms')
    parser.add_argument("--port", type=int, default=None,
                        help='Port filter for TCP/UDP (reserved)')
    parser.add_argument("--stats-interval", type=int, default=5,
                        help='Stats interval in seconds for stats mode (reserved)')

    # Global config
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--generate-traffic", action="store_true")
    parser.add_argument("--ping-interval", type=float, default=1)
    parser.add_argument("--timeout-ms", type=int, default=1000, help="Drop detection timeout (ms)")
    parser.add_argument("--receiver-warmup", type=int, default=2)
    parser.add_argument("--shutdown-wait", type=int, default=3)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--json-only", action="store_true", help="(deprecated) Use --json instead")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Markdown report")

    return parser.parse_args()


def validate_args(args):
    """Validate argument combinations."""
    # MVP: Only ICMP is fully implemented
    if args.protocol != 'icmp':
        print(f"Warning: Protocol '{args.protocol}' is reserved for future implementation. Using ICMP.",
              file=sys.stderr)
        args.protocol = 'icmp'

    # Stats mode only for TCP/UDP (reserved)
    if args.output_mode == 'stats' and args.protocol == 'icmp':
        print("Warning: Stats mode not supported for ICMP. Using verbose.", file=sys.stderr)
        args.output_mode = 'verbose'

    # Port filter only for TCP/UDP
    if args.port is not None and args.protocol == 'icmp':
        print("Warning: Port filter ignored for ICMP protocol.", file=sys.stderr)
        args.port = None

    return args


def main():
    args = parse_args()
    args = validate_args(args)
    # --json-only is deprecated, use --json
    output_json = args.json or args.json_only
    quiet = output_json

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    measurement_dir = args.output_dir if args.output_dir else f"./measurement-{timestamp}"
    os.makedirs(measurement_dir, exist_ok=True)

    # Build environment for shell scripts
    env = {
        "SENDER_HOST_SSH": args.sender_host_ssh,
        "SENDER_IP": args.sender_ip,
        "SENDER_PHY_IF": args.sender_phy_if,
        "RECEIVER_HOST_SSH": args.receiver_host_ssh,
        "RECEIVER_IP": args.receiver_ip,
        "RECEIVER_PHY_IF": args.receiver_phy_if,
        "LOCAL_TOOLS": args.local_tools_path,
        "DURATION": str(args.duration),
        "TIMEOUT_MS": str(args.timeout_ms),
        "MEASUREMENT_DIR": measurement_dir,
        "RECEIVER_WARMUP": str(args.receiver_warmup),
        "SHUTDOWN_WAIT": str(args.shutdown_wait),
        # v2: Protocol and mode env vars
        "PROTOCOL": args.protocol,
        "DIRECTION": args.direction,
        "FOCUS": args.focus,
        "OUTPUT_MODE": args.output_mode,
        "TOOL_NAME": get_tool_name(args.protocol),
    }

    # Optional parameters
    if args.port is not None:
        env["PORT"] = str(args.port)
    if args.stats_interval:
        env["STATS_INTERVAL"] = str(args.stats_interval)

    # Step 1: Validate SSH
    if not args.skip_validate:
        if not quiet:
            print("\n[Validate] Checking SSH connectivity...")
        for name, ssh_addr in [("Sender Host", args.sender_host_ssh), ("Receiver Host", args.receiver_host_ssh)]:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", ssh_addr, "echo ok"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"Error: Cannot SSH to {name} ({ssh_addr})", file=sys.stderr)
                sys.exit(1)
            if not quiet:
                print(f"  {name} ({ssh_addr}): OK")

    # Step 2: Start traffic (sender pings receiver)
    traffic_proc = None
    if args.generate_traffic:
        if not quiet:
            print(f"\n[Traffic] Starting ping {args.sender_ip} -> {args.receiver_ip}")
        traffic_proc = subprocess.Popen(
            ["ssh", args.sender_host_ssh, f"ping -i {args.ping_interval} {args.receiver_ip}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    try:
        # Step 3: Deploy
        if not args.skip_deploy:
            result = run_script("deploy_tools.sh", env, "Deploying BPF tools", quiet)
            if result.returncode != 0:
                print("Error: Tool deployment failed", file=sys.stderr)
                sys.exit(1)

        # Step 4-6: Measure
        if not quiet:
            print(f"\n[Config] Protocol={args.protocol}, Direction={args.direction}, "
                  f"Focus={args.focus}, OutputMode={args.output_mode}")
        result = run_script("start_measurement.sh", env, "Running measurement", quiet)
        if result.returncode != 0:
            print("Error: Measurement failed", file=sys.stderr)
            sys.exit(1)
    finally:
        # Step 7: Stop traffic (always cleanup, even on failure)
        if traffic_proc:
            traffic_proc.terminate()
            try:
                traffic_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                traffic_proc.kill()
            if not quiet:
                print("[Traffic] Stopped.")

    # Step 8: Output measurement info (no analysis - use system-network-latency-analysis skill)
    result = {
        "status": "success",
        "measurement_dir": measurement_dir,
        "log_files": ["sender-host.log", "receiver-host.log"],
        "protocol": args.protocol,
        "direction": args.direction,
        "focus": args.focus,
        "duration": args.duration,
    }

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        print("[Complete] Measurement finished")
        print(f"{'='*60}")
        print(f"Output directory: {measurement_dir}")
        print(f"Log files: sender-host.log, receiver-host.log")
        print(f"\nTo analyze: python3 .claude/skills/system-network-latency-analysis/scripts/generate_report.py {measurement_dir}")


if __name__ == "__main__":
    main()
