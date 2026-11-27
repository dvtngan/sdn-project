#!/usr/bin/env python3
"""
Remove the DNS-hijack flows installed by push_dns_hijack.py.

Deletes every flow tagged with our application id (org.sdnproject.dnshijack)
via the ONOS REST API, returning the network to normal. Clean teardown for
repeatable measurements.

Usage:
    python3 remove_dns_hijack.py
"""
import base64
import os
import sys
import urllib.request
import urllib.error

ONOS_HOST = os.environ.get("ONOS_HOST", "127.0.0.1")
ONOS_PORT = os.environ.get("ONOS_PORT", "8181")
ONOS_USER = os.environ.get("ONOS_USER", "onos")
ONOS_PASS = os.environ.get("ONOS_PASS", "rocks")
APP_ID    = "org.sdnproject.dnshijack"

BASE = f"http://{ONOS_HOST}:{ONOS_PORT}/onos/v1"


def main():
    raw = f"{ONOS_USER}:{ONOS_PASS}".encode()
    auth = "Basic " + base64.b64encode(raw).decode()
    req = urllib.request.Request(
        f"{BASE}/flows/application/{APP_ID}", method="DELETE")
    req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"[+] Removed DNS-hijack flows (app {APP_ID}): HTTP {r.status}")
    except urllib.error.URLError as e:
        sys.exit(f"[!] Could not reach ONOS ({e}).")


if __name__ == "__main__":
    main()
