#!/usr/bin/env python3
"""VM Latency Measurement - Main Entry Point.

This script orchestrates the complete measurement workflow:
1. Validate SSH connectivity
2. Start background traffic (if --generate-traffic)
3. Deploy BPF tools to targets
4. Start 8 measurement tools in parallel
5. Wait for measurement duration
6. Stop tools and collect logs
7. Stop background traffic (if started)
8. Parse logs and output JSON

Usage:
    python measure.py --sender-vm-ssh root@10.0.0.1 --sender-vm-ip 10.0.0.1 \\
                      --sender-host-ssh root@192.168.1.10 \\
                      --receiver-vm-ssh root@10.0.0.2 --receiver-vm-ip 10.0.0.2 \\
                      --receiver-host-ssh root@192.168.1.20 \\
                      --send-vnet-if vnet0 --send-phy-if enp0s0 --send-vm-if ens4 \\
                      --recv-vnet-if vnet1 --recv-phy-if enp0s0 --recv-vm-if ens4 \\
                      --local-tools-path /opt/troubleshooting-tools/measurement-tools \\
                      --generate-traffic --duration 30
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_script_dir() -> Path:
    """Get the directory containing this script."""
    return Path(__file__).parent.resolve()


def run_script(script_name: str, env: dict, description: str, quiet: bool = False) -> subprocess.CompletedProcess:
    """Run a shell script with the given environment."""
    script_path = get_script_dir() / script_name

    if not script_path.exists():
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print(f"\n{'='*60}")
        print(f"[Step] {description}")
        print(f"{'='*60}")

    result = subprocess.run(
        ["bash", str(script_path)],
        env={**os.environ, **env},
        capture_output=False,
    )

    return result


def create_env_dict(args: argparse.Namespace) -> dict:
    """Convert argparse namespace to environment variables dict."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    measurement_dir = args.output_dir if args.output_dir else f"./measurement-{timestamp}"

    return {
        # L2 environment parameters
        "SENDER_VM_SSH": args.sender_vm_ssh,
        "SENDER_VM_IP": args.sender_vm_ip,
        "SENDER_HOST_SSH": args.sender_host_ssh,
        "SEND_VNET_IF": args.send_vnet_if,
        "SEND_PHY_IF": args.send_phy_if,
        "SEND_VM_IF": args.send_vm_if,
        "RECEIVER_VM_SSH": args.receiver_vm_ssh,
        "RECEIVER_VM_IP": args.receiver_vm_ip,
        "RECEIVER_HOST_SSH": args.receiver_host_ssh,
        "RECV_VNET_IF": args.recv_vnet_if,
        "RECV_PHY_IF": args.recv_phy_if,
        "RECV_VM_IF": args.recv_vm_if,
        "LOCAL_TOOLS": args.local_tools_path,
        # Global configuration parameters
        "DURATION": str(args.duration),
        "GENERATE_TRAFFIC": "true" if args.generate_traffic else "false",
        "RECEIVER_WARMUP": str(args.receiver_warmup),
        "SHUTDOWN_WAIT": str(args.shutdown_wait),
        "PING_INTERVAL": str(args.ping_interval),
        # Derived values
        "MEASUREMENT_DIR": measurement_dir,
        "TIMESTAMP": timestamp,
    }


def validate_ssh_connectivity(env: dict) -> bool:
    """Validate SSH connectivity to all 4 machines."""
    print("\n[Validating SSH connectivity]")

    targets = [
        ("Sender VM", env["SENDER_VM_SSH"]),
        ("Sender Host", env["SENDER_HOST_SSH"]),
        ("Receiver VM", env["RECEIVER_VM_SSH"]),
        ("Receiver Host", env["RECEIVER_HOST_SSH"]),
    ]

    all_ok = True
    for name, ssh_target in targets:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             ssh_target, "echo OK"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  {name} ({ssh_target}): OK")
        else:
            print(f"  {name} ({ssh_target}): FAILED")
            all_ok = False

    return all_ok


def start_background_traffic(env: dict, quiet: bool = False) -> subprocess.Popen | None:
    """Start background ping traffic from sender VM to receiver VM.

    Returns the Popen object for the SSH process, or None if not started.
    """
    if env.get("GENERATE_TRAFFIC") != "true":
        return None

    if not quiet:
        print(f"\n{'='*60}")
        print("[Step] Starting background traffic")
        print(f"{'='*60}")

    sender_vm_ssh = env["SENDER_VM_SSH"]
    receiver_vm_ip = env["RECEIVER_VM_IP"]
    ping_interval = env.get("PING_INTERVAL", "1")

    # Calculate total traffic duration: measurement + buffer
    duration = int(env.get("DURATION", "30"))
    receiver_warmup = int(env.get("RECEIVER_WARMUP", "2"))
    shutdown_wait = int(env.get("SHUTDOWN_WAIT", "3"))

    # Total time = warmup + duration + shutdown + buffer
    total_time = receiver_warmup + duration + shutdown_wait + 10
    ping_count = int(total_time / float(ping_interval)) + 10

    if not quiet:
        print(f"  Ping: {sender_vm_ssh} -> {receiver_vm_ip}")
        print(f"  Count: {ping_count}, Interval: {ping_interval}s")

    # Start ping in background via SSH
    # Use nohup and redirect to prevent SSH from hanging
    cmd = [
        "ssh", sender_vm_ssh,
        f"nohup ping -c {ping_count} -i {ping_interval} {receiver_vm_ip} > /tmp/bg_ping.log 2>&1 &"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        if not quiet:
            print("  Background ping started")
        return True  # Return truthy value to indicate traffic was started
    else:
        print(f"  Warning: Failed to start background ping: {result.stderr}", file=sys.stderr)
        return None


def stop_background_traffic(env: dict, quiet: bool = False):
    """Stop background ping traffic on sender VM."""
    if env.get("GENERATE_TRAFFIC") != "true":
        return

    if not quiet:
        print(f"\n{'='*60}")
        print("[Step] Stopping background traffic")
        print(f"{'='*60}")

    sender_vm_ssh = env["SENDER_VM_SSH"]

    # Kill ping process on sender VM
    subprocess.run(
        ["ssh", sender_vm_ssh, "pkill -f 'ping.*-c.*-i'"],
        capture_output=True,
    )

    if not quiet:
        print("  Background ping stopped")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Execute coordinated VM latency measurement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python measure.py \\
        --sender-vm-ssh root@192.168.77.83 \\
        --sender-vm-ip 192.168.77.83 \\
        --sender-host-ssh smartx@192.168.70.32 \\
        --send-vnet-if vnet35 \\
        --send-phy-if enp24s0f0np0 \\
        --send-vm-if ens4 \\
        --receiver-vm-ssh root@192.168.76.244 \\
        --receiver-vm-ip 192.168.76.244 \\
        --receiver-host-ssh smartx@192.168.70.31 \\
        --recv-vnet-if vnet130 \\
        --recv-phy-if enp24s0f0np0 \\
        --recv-vm-if ens4 \\
        --local-tools-path ~/workspace/troubleshooting-tools/measurement-tools \\
        --generate-traffic \\
        --duration 30
        """
    )

    # Sender configuration (L2 environment parameters)
    sender_group = parser.add_argument_group("Sender Configuration (L2 env)")
    sender_group.add_argument("--sender-vm-ssh", required=True,
                              help="SSH address for sender VM (e.g., root@10.0.0.1)")
    sender_group.add_argument("--sender-vm-ip", required=True,
                              help="Sender VM IP address for BPF filter")
    sender_group.add_argument("--sender-host-ssh", required=True,
                              help="SSH address for sender host")
    sender_group.add_argument("--send-vnet-if", required=True,
                              help="Sender VM's TAP interface on host (e.g., vnet0)")
    sender_group.add_argument("--send-phy-if", required=True,
                              help="Sender host physical NIC (e.g., enp0s0)")
    sender_group.add_argument("--send-vm-if", required=True,
                              help="Sender VM's internal NIC (e.g., ens4)")

    # Receiver configuration (L2 environment parameters)
    receiver_group = parser.add_argument_group("Receiver Configuration (L2 env)")
    receiver_group.add_argument("--receiver-vm-ssh", required=True,
                                help="SSH address for receiver VM")
    receiver_group.add_argument("--receiver-vm-ip", required=True,
                                help="Receiver VM IP address for BPF filter")
    receiver_group.add_argument("--receiver-host-ssh", required=True,
                                help="SSH address for receiver host")
    receiver_group.add_argument("--recv-vnet-if", required=True,
                                help="Receiver VM's TAP interface on host")
    receiver_group.add_argument("--recv-phy-if", required=True,
                                help="Receiver host physical NIC")
    receiver_group.add_argument("--recv-vm-if", required=True,
                                help="Receiver VM's internal NIC")

    # Tool configuration
    tool_group = parser.add_argument_group("Tool Configuration")
    tool_group.add_argument("--local-tools-path", required=True,
                            help="Local path to BPF measurement tools")

    # Global configuration parameters
    config_group = parser.add_argument_group("Global Configuration")
    config_group.add_argument("--duration", type=int, default=30,
                              help="Measurement duration in seconds (default: 30)")
    config_group.add_argument("--generate-traffic", action="store_true",
                              help="Generate test traffic (ping) from sender VM")
    config_group.add_argument("--receiver-warmup", type=int, default=2,
                              help="Receiver tools warmup time in seconds (default: 2)")
    config_group.add_argument("--shutdown-wait", type=int, default=3,
                              help="Graceful shutdown wait time in seconds (default: 3)")
    config_group.add_argument("--ping-interval", type=float, default=1,
                              help="Ping interval in seconds, only with --generate-traffic (default: 1)")

    # Skip flags
    skip_group = parser.add_argument_group("Skip Options")
    skip_group.add_argument("--skip-deploy", action="store_true",
                            help="Skip tool deployment (tools already deployed)")
    skip_group.add_argument("--skip-validate", action="store_true",
                            help="Skip SSH validation")

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument("--output-dir", type=str, default=None,
                              help="Output directory (default: ./measurement-TIMESTAMP)")
    output_group.add_argument("--json-only", action="store_true",
                              help="Only output final JSON, suppress progress")

    return parser.parse_args()


def main():
    args = parse_args()
    env = create_env_dict(args)
    quiet = args.json_only

    # Create measurement directory
    measurement_dir = Path(env["MEASUREMENT_DIR"])
    measurement_dir.mkdir(parents=True, exist_ok=True)

    # Save command log
    cmdlog_path = measurement_dir / "commands.log"
    with open(cmdlog_path, "w") as f:
        f.write(f"=== Measurement Commands Log ===\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Measurement Directory: {measurement_dir}\n\n")
        f.write("Environment Variables:\n")
        for key, value in sorted(env.items()):
            f.write(f"  {key}={value}\n")
        f.write("\n")

    if not quiet:
        print(f"Measurement directory: {measurement_dir}")
        print(f"Traffic generation: {'enabled' if args.generate_traffic else 'disabled (using background traffic)'}")

    # Step 1: Validate SSH connectivity
    if not args.skip_validate:
        if not validate_ssh_connectivity(env):
            print("\nError: SSH connectivity check failed", file=sys.stderr)
            sys.exit(1)

    # Step 2: Start background traffic (if enabled)
    # This ensures traffic flows during discovery and measurement
    traffic_started = start_background_traffic(env, quiet)

    try:
        # Step 3: Deploy tools
        if not args.skip_deploy:
            result = run_script("deploy_tools.sh", env, "Deploying BPF tools", quiet)
            if result.returncode != 0:
                print("\nError: Tool deployment failed", file=sys.stderr)
                sys.exit(1)

        # Step 4: Start measurement (all 8 tools in parallel)
        result = run_script("start_measurement.sh", env, "Starting 8 measurement tools", quiet)
        if result.returncode != 0:
            print("\nError: Measurement failed", file=sys.stderr)
            sys.exit(1)

    finally:
        # Step 5: Stop background traffic (if started)
        if traffic_started:
            stop_background_traffic(env, quiet)

    # Step 6: Parse logs
    if not quiet:
        print(f"\n{'='*60}")
        print("[Step] Parsing measurement logs")
        print(f"{'='*60}")

    parse_script = get_script_dir() / "parse_measurement_logs.py"
    result = subprocess.run(
        [sys.executable, str(parse_script), str(measurement_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error parsing logs: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Output JSON result
    print(result.stdout)

    if not quiet:
        print(f"\n{'='*60}")
        print(f"Measurement complete. Logs saved to: {measurement_dir}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
