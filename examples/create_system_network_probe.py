#!/usr/bin/env python3

"""
Create System Network Probe Task - NetSherlock

This script demonstrates how to create a system network (host-to-host)
network probe diagnosis task via the NetSherlock API.

Usage:
    python3 create_system_network_probe.py latency
    python3 create_system_network_probe.py packet_drop
    python3 create_system_network_probe.py connectivity

Environment Variables:
    API_URL: Backend API endpoint (default: http://localhost:8000)
    API_KEY: API authentication key (default: test-key-12345)
    SRC_HOST: Source host IP (default: 192.168.79.11)
    DST_HOST: Destination host IP (default: 192.168.79.12)
"""

import os
import sys
import json
import argparse
from typing import Optional
import requests
from datetime import datetime

# Configuration
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_API_KEY = "test-key-12345"
DEFAULT_SRC_HOST = "192.168.79.11"
DEFAULT_DST_HOST = "192.168.79.12"

# ANSI colors
class Colors:
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'  # No Color


def print_header():
    """Print script header."""
    print(f"{Colors.BLUE}╔════════════════════════════════════════════════════════════╗{Colors.NC}")
    print(f"{Colors.BLUE}║{Colors.NC}  Creating System Network Probe Diagnosis Task            {Colors.BLUE}║{Colors.NC}")
    print(f"{Colors.BLUE}╚════════════════════════════════════════════════════════════╝{Colors.NC}")
    print()


def print_section(title: str):
    """Print section header."""
    print(f"{Colors.YELLOW}{title}{Colors.NC}")


def print_success(message: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {message}{Colors.NC}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {message}{Colors.NC}")


def print_info(message: str, indent: str = "  "):
    """Print info message."""
    print(f"{indent}• {message}")


def validate_probe_type(probe_type: str) -> bool:
    """Validate probe type."""
    return probe_type in ["latency", "packet_drop", "connectivity"]


def create_diagnosis_request(
    probe_type: str,
    src_host: str,
    dst_host: str,
    mode: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Create diagnosis request body."""
    request = {
        "network_type": "system",
        "diagnosis_type": probe_type,
        "src_host": src_host,
        "dst_host": dst_host,
    }
    
    if mode:
        request["mode"] = mode
    
    if description:
        request["description"] = description
    else:
        request["description"] = (
            f"System network {probe_type} probe from {src_host} to {dst_host}"
        )
    
    return request


def submit_diagnosis(
    api_url: str,
    api_key: str,
    request_body: dict,
) -> Optional[dict]:
    """Submit diagnosis request to API."""
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.post(
            f"{api_url}/diagnose",
            headers=headers,
            json=request_body,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return None


def print_next_steps(diagnosis_id: str, api_url: str, api_key: str):
    """Print next steps after successful task creation."""
    print()
    print(f"{Colors.BLUE}🔍 Next Steps:{Colors.NC}")
    print()
    
    print_info("Check task status:")
    print(f'    curl -H "X-API-Key: {api_key}" "{api_url}/diagnose/{diagnosis_id}"')
    print()
    
    print_info("List all tasks:")
    print(f'    curl -H "X-API-Key: {api_key}" "{api_url}/diagnoses?limit=10"')
    print()
    
    print_info("Get diagnosis report (after completion):")
    print(f'    curl -H "X-API-Key: {api_key}" "{api_url}/diagnose/{diagnosis_id}/report"')
    print()
    
    print_info("Cancel the task (if still pending/waiting):")
    print(f'    curl -X POST -H "X-API-Key: {api_key}" "{api_url}/diagnose/{diagnosis_id}/cancel"')
    print()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Create a system network probe diagnosis task"
    )
    parser.add_argument(
        "probe_type",
        nargs="?",
        default="latency",
        choices=["latency", "packet_drop", "connectivity"],
        help="Type of probe: latency, packet_drop, or connectivity",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_URL", DEFAULT_API_URL),
        help="Backend API endpoint",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("API_KEY", DEFAULT_API_KEY),
        help="API authentication key",
    )
    parser.add_argument(
        "--src-host",
        default=os.getenv("SRC_HOST", DEFAULT_SRC_HOST),
        help="Source host IP",
    )
    parser.add_argument(
        "--dst-host",
        default=os.getenv("DST_HOST", DEFAULT_DST_HOST),
        help="Destination host IP",
    )
    parser.add_argument(
        "--mode",
        choices=["autonomous", "interactive"],
        help="Diagnosis mode (optional)",
    )
    parser.add_argument(
        "--description",
        help="Additional problem description (optional)",
    )
    
    args = parser.parse_args()
    
    # Print header
    print_header()
    
    # Validate probe type
    if not validate_probe_type(args.probe_type):
        print_error(f"Invalid probe type: {args.probe_type}")
        print(f"Valid types: latency, packet_drop, connectivity")
        sys.exit(1)
    
    # Print configuration
    print_section("📋 Task Configuration:")
    print_info("Network Type: system (host-to-host)")
    print_info(f"Diagnosis Type: {args.probe_type}")
    print_info(f"Source Host: {args.src_host}")
    print_info(f"Destination Host: {args.dst_host}")
    print_info(f"API URL: {args.api_url}")
    if args.mode:
        print_info(f"Mode: {args.mode}")
    print()
    
    # Create request
    print_section("📨 Sending Request:")
    request_body = create_diagnosis_request(
        probe_type=args.probe_type,
        src_host=args.src_host,
        dst_host=args.dst_host,
        mode=args.mode,
        description=args.description,
    )
    print(f"  POST {args.api_url}/diagnose")
    print("  Headers:")
    print(f"    - X-API-Key: {args.api_key}")
    print("    - Content-Type: application/json")
    print()
    print("  Body:")
    print(json.dumps(request_body, indent=4))
    print()
    
    # Submit request
    print_section("⏳ Waiting for response...")
    print()
    
    response = submit_diagnosis(args.api_url, args.api_key, request_body)
    
    if response:
        print_success("Task created successfully!")
        print()
        
        # Print response
        print_section("📊 Response:")
        print(json.dumps(response, indent=2))
        print()
        
        # Extract diagnosis ID
        diagnosis_id = response.get("diagnosis_id")
        if diagnosis_id:
            print_success(f"Diagnosis ID: {diagnosis_id}")
            print_next_steps(diagnosis_id, args.api_url, args.api_key)
        
        print(f"{Colors.BLUE}╔════════════════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.BLUE}║{Colors.NC}  Task creation complete!                                 {Colors.BLUE}║{Colors.NC}")
        print(f"{Colors.BLUE}╚════════════════════════════════════════════════════════════╝{Colors.NC}")
    else:
        print_error("Failed to create task")
        sys.exit(1)


if __name__ == "__main__":
    main()
