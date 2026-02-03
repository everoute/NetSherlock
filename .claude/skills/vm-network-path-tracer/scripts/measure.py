#!/usr/bin/env python3
"""VM Network Path Tracer - Main Entry Point (v2).

Deploys *_path_tracer.py to sender and receiver hosts for
VM traffic drop detection and latency measurement at vnet↔phy boundaries.

v2 additions:
- Multi-protocol support: ICMP (MVP), TCP/UDP (reserved)
- Focus mode: drop (丢包定界) vs latency (延迟定界)
- Output mode: verbose (per-packet) vs stats (periodic histograms)
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
        'icmp': 'icmp_path_tracer.py',
        'tcp': 'tcp_path_tracer.py',
        'udp': 'udp_path_tracer.py'
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
        description="VM Network Path Tracer (v2)"
    )

    # L2 environment
    parser.add_argument("--sender-host-ssh", required=True)
    parser.add_argument("--sender-vm-ip", required=True, help="Sender VM IP for BPF filter")
    parser.add_argument("--receiver-vm-ip", required=True, help="Receiver VM IP for BPF filter")
    parser.add_argument("--send-vnet-if", required=True, help="Sender VM TAP interface (e.g. vnet35)")
    parser.add_argument("--sender-phy-if", required=True)
    parser.add_argument("--receiver-host-ssh", required=True)
    parser.add_argument("--recv-vnet-if", required=True, help="Receiver VM TAP interface (e.g. vnet130)")
    parser.add_argument("--receiver-phy-if", required=True)
    parser.add_argument("--local-tools-path", required=True)

    # v2: Protocol and mode parameters
    parser.add_argument("--protocol", choices=['icmp', 'tcp', 'udp'], default='icmp',
                        help='Protocol to trace (default: icmp). Note: TCP/UDP reserved for future.')
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
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--receiver-warmup", type=int, default=2)
    parser.add_argument("--shutdown-wait", type=int, default=3)
    parser.add_argument("--skip-deploy", action="store_true")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--sender-vm-ssh", default="", help="Sender VM SSH (for --generate-traffic from VM)")

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
    quiet = args.json_only

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    measurement_dir = args.output_dir if args.output_dir else f"./measurement-{timestamp}"
    os.makedirs(measurement_dir, exist_ok=True)

    # Build environment for shell scripts
    env = {
        "SENDER_HOST_SSH": args.sender_host_ssh,
        "SENDER_VM_IP": args.sender_vm_ip,
        "RECEIVER_VM_IP": args.receiver_vm_ip,
        "SEND_VNET_IF": args.send_vnet_if,
        "SENDER_PHY_IF": args.sender_phy_if,
        "RECEIVER_HOST_SSH": args.receiver_host_ssh,
        "RECV_VNET_IF": args.recv_vnet_if,
        "RECEIVER_PHY_IF": args.receiver_phy_if,
        "LOCAL_TOOLS": args.local_tools_path,
        "DURATION": str(args.duration),
        "TIMEOUT_MS": str(args.timeout_ms),
        "MEASUREMENT_DIR": measurement_dir,
        "RECEIVER_WARMUP": str(args.receiver_warmup),
        "SHUTDOWN_WAIT": str(args.shutdown_wait),
        # v2: Protocol and mode env vars
        "PROTOCOL": args.protocol,
        "FOCUS": args.focus,
        "OUTPUT_MODE": args.output_mode,
        "TOOL_NAME": get_tool_name(args.protocol),
    }

    # Optional parameters
    if args.port is not None:
        env["PORT"] = str(args.port)
    if args.stats_interval:
        env["STATS_INTERVAL"] = str(args.stats_interval)

    # Validate SSH (hosts only)
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

    # Traffic generation
    traffic_proc = None
    if args.generate_traffic:
        traffic_ssh = args.sender_vm_ssh if args.sender_vm_ssh else args.sender_host_ssh
        traffic_src = "VM" if args.sender_vm_ssh else "Host"
        if not quiet:
            print(f"\n[Traffic] Starting ping from {traffic_src} to {args.receiver_vm_ip}")
        traffic_proc = subprocess.Popen(
            ["ssh", traffic_ssh, f"ping -i {args.ping_interval} {args.receiver_vm_ip}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    try:
        if not args.skip_deploy:
            result = run_script("deploy_tools.sh", env, "Deploying BPF tools", quiet)
            if result.returncode != 0:
                print("Error: Tool deployment failed", file=sys.stderr)
                sys.exit(1)

        if not quiet:
            print(f"\n[Config] Protocol={args.protocol}, Focus={args.focus}, OutputMode={args.output_mode}")
        result = run_script("start_measurement.sh", env, "Running measurement", quiet)
        if result.returncode != 0:
            print("Error: Measurement failed", file=sys.stderr)
            sys.exit(1)
    finally:
        if traffic_proc:
            traffic_proc.terminate()
            try:
                traffic_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                traffic_proc.kill()
            if not quiet:
                print("[Traffic] Stopped.")

    if not quiet:
        print(f"\n{'='*60}")
        print("[Step] Parsing measurement logs")
        print(f"{'='*60}")

    sys.path.insert(0, str(get_script_dir()))
    from parse_logs import parse_vm_drop_logs

    # Pass protocol and mode info to parser
    result_json = parse_vm_drop_logs(
        measurement_dir,
        protocol=args.protocol,
        focus=args.focus,
        output_mode=args.output_mode
    )
    print(json.dumps(result_json, indent=2))


if __name__ == "__main__":
    main()
