#!/usr/bin/env python3
"""
Simulate Alertmanager webhook to test NetSherlock system network integration.

This script sends a fake Alertmanager webhook payload that mimics what Prometheus
would send when host_to_host_max_ping_time_ns:critical alert fires.

Usage:
    # Start netsherlock webhook server first:
    WEBHOOK_API_KEY=test-key WEBHOOK_ALLOW_INSECURE=false \
    GLOBAL_INVENTORY_PATH=config/global_inventory.yaml \
    python -m netsherlock.api.webhook

    # Then run this script:
    python scripts/test_alertmanager_webhook.py

    # Or with custom settings:
    WEBHOOK_URL=http://localhost:8080/webhook/alertmanager \
    API_KEY=test-key \
    python scripts/test_alertmanager_webhook.py
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

# Configuration from environment or defaults
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8080/webhook/alertmanager")
API_KEY = os.environ.get("API_KEY", "test-key")

# Simulate alert from host_to_host_max_ping_time_ns:critical
# Using labels that match the actual Prometheus metric
ALERT_PAYLOAD = {
    "version": "4",
    "groupKey": "{}:{alertname=\"host_to_host_max_ping_time_ns:critical\"}",
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "netsherlock",
    "groupLabels": {
        "alertname": "host_to_host_max_ping_time_ns:critical"
    },
    "commonLabels": {
        "alertname": "host_to_host_max_ping_time_ns:critical",
        "network_type": "system",
        "severity": "critical",
    },
    "commonAnnotations": {
        "summary": "High storage network P90 latency between hosts",
    },
    "externalURL": "http://70.0.0.31:9090",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                # Alert name - maps to diagnosis type via _map_alert_to_type()
                "alertname": "host_to_host_max_ping_time_ns:critical",
                # Source and destination hostnames (from Prometheus metric labels)
                "hostname": "node31",
                "to_hostname": "node32",
                # Network type for webhook routing
                "network_type": "system",
                # Original metric labels
                "_host": "23021eac-d6e5-11ed-802d-5254002fc8dd",
                "_to_host": "66cb384e-d6e5-11ed-9faf-525400111812",
                "instance": "70.0.0.31:10404",
                "job": "tuna-exporter.network_gruff_metrics",
                # Severity
                "severity": "critical",
            },
            "annotations": {
                "summary": "High storage network P90 latency: node31 → node32",
                "description": "P90 ping latency 6.5ms exceeds 5ms threshold",
                "src_hostname": "node31",
                "dst_hostname": "node32",
            },
            "startsAt": datetime.now(timezone.utc).isoformat(),
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://70.0.0.31:9090/graph?...",
            "fingerprint": "abc123def456",
        }
    ],
}


def main():
    print(f"Sending test alert to {WEBHOOK_URL}")
    print(f"API Key: {API_KEY[:8]}...")
    print()
    print("Alert payload:")
    print(json.dumps(ALERT_PAYLOAD["alerts"][0]["labels"], indent=2))
    print()

    try:
        response = requests.post(
            WEBHOOK_URL,
            json=ALERT_PAYLOAD,
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        print(f"Status: {response.status_code}")
        print(f"Response:")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print(response.text)

        if response.status_code == 200:
            # Extract diagnosis_id for follow-up query
            data = response.json()
            if data and len(data) > 0:
                diagnosis_id = data[0].get("diagnosis_id")
                if diagnosis_id:
                    print()
                    print("=" * 60)
                    print(f"Diagnosis queued! ID: {diagnosis_id}")
                    print()
                    print("To check status:")
                    print(f'  curl -H "X-API-Key: {API_KEY}" \\')
                    print(f"    {WEBHOOK_URL.rsplit('/', 2)[0]}/diagnose/{diagnosis_id}")
                    print("=" * 60)

        return response.status_code == 200

    except requests.exceptions.ConnectionError:
        print(f"ERROR: Could not connect to {WEBHOOK_URL}")
        print("Make sure the netsherlock webhook server is running:")
        print()
        print("  WEBHOOK_API_KEY=test-key \\")
        print("  GLOBAL_INVENTORY_PATH=config/global_inventory.yaml \\")
        print("  python -m netsherlock.api.webhook")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
