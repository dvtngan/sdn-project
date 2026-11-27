<div align="center">

# Implementation and Analysis of Man-in-the-Middle Attacks in SDN

**Security of Software-Defined Networking**

![Mininet](https://img.shields.io/badge/Mininet-emulation-blue)
![ONOS](https://img.shields.io/badge/ONOS-2.7.0-orange)
![OpenFlow](https://img.shields.io/badge/OpenFlow-1.3-green)
![OVS](https://img.shields.io/badge/Open%20vSwitch-data%20plane-lightgrey)
![Python](https://img.shields.io/badge/Python-3-yellow)
![License](https://img.shields.io/badge/Use-Educational%20only-red)

</div>

---

## Disclaimer

This repository contains **educational and research material** demonstrating Man-in-the-Middle (MitM) attacks in a controlled SDN environment. Every experiment runs in an isolated Mininet simulation with a local ONOS controller — never against a production network. Unauthorized access to computer systems is illegal. Do not use this material against systems you do not own or do not have explicit permission to test.

---

## Overview

Software-Defined Networking (SDN) separates the **control plane** (routing logic, topology awareness, policy) from the **data plane** (switches forwarding at line rate). A logically centralized controller holds a global view of the topology and programs the switches by installing flow rules over a southbound protocol, most commonly OpenFlow. That centralization makes the network programmable, but it also moves the adversary's most valuable target from individual hosts to the **controller itself**.

To maintain its global view, an SDN controller continuously ingests unauthenticated signals: LLDP frames to map links, OpenFlow `PACKET_IN` messages to discover hosts, and ARP exchanges to learn L2/L3 reachability. Standard controller services accept these inputs with little or no verification, so forged packets can corrupt the controller's internal state — and the controller then computes and installs flow rules that route victim traffic through the attacker. Interception becomes **network-wide and stealthier** than a local LAN trick.

This project implements and compares **three MitM attacks on one shared testbed**, each aimed at a different trust assumption in the SDN stack:

| # | Attack | SDN layer targeted | Attacker privilege | Interception |
|---|--------|--------------------|--------------------|:------------:|
| 1 | **ARP Spoofing / Cache Poisoning** | Host ARP cache (L2); also poisons the ONOS host table | LAN host, no controller access | 100% |
| 2 | **DNS Hijacking (MitM)** | Control-plane flow table on the switch, via the ONOS REST API | LAN host **+ ONOS REST credentials** | 100% |
| 3 | **Host-Location Hijacking (MitM)** | The ONOS host-tracking table (Host Location Provider) | LAN host, no controller access | 100% |

**Key findings:** all three reach 100% interception, so the question is not *whether* they work but *how easily and how quietly*. Weighing impact against the privilege required, **host-location hijacking is the greatest weakness**, it needs only an unprivileged host on the victim's forwarding path, yet it corrupts the controller's own record of where the victim is and yields a full MitM. The common thread across all three: the controller trusts unauthenticated data-plane input (ARP replies, `PACKET_IN`, host-location signals) and acts on it automatically.

---

## Repository Structure

Each attack is self-contained in its own folder with a dedicated run guide.

```
sdn-project/
├── README.md                          # This file
│
├── arp-spoofing/                      # Attack 1 — ARP spoofing / cache poisoning
│   ├── arp_topo.py                    # Mininet topology (LAN A, connects to ONOS)
│   ├── arp_attack.py                  # Scapy ARP poisoning script (runs on the attacker)
│   └── RUN.md                         # Step-by-step run guide
│
├── dns-hijacking/                     # Attack 2 — DNS man-in-the-middle via OpenFlow
│   ├── dns_topo.py                    # Mininet topology (3 LANs + router, OF1.3)
│   ├── scripts/
│   │   ├── push_dns_hijack.py         # Installs the two DNS-steering flows via ONOS REST API
│   │   ├── remove_dns_hijack.py       # Removes them via ONOS REST API
│   │   ├── dns_hijack.sh              # Fallback: install flows with ovs-ofctl (no controller)
│   │   ├── dns_restore.sh             # Fallback: remove the ovs-ofctl flows
│   │   ├── dnsmasq-legit.conf         # Real resolver config (host srv)
│   │   └── dnsmasq-proxy.conf         # Attacker proxy config (host h3) — forwards + tampers one record
│   ├── RUN.md                         # Step-by-step run guide
│   └── REPORT_M3_DNS_MITM.md          # Detailed write-up of the DNS MitM
│
└── host-location-hijacking/           # Attack 3 — host-location hijacking (MitM)
    ├── hlh_topo.py                    # Testbed (3 LANs + router; attacker on the victim's switch)
    ├── hlh_mitm.py                    # Full MitM — adopts victim identity, poisons continuously
    ├── hlh_attack.py                  # One-shot — flips the victim's host-table entry once
    ├── hlh_attack_sustained.py        # Keeps re-poisoning (no identity change)
    └── README.md                      # Step-by-step run guide
```

---

## Branching Model

`main` contains all three attacks combined (this README). Each attack also keeps its own development branch:

| Branch | Contents |
|--------|----------|
| `main` | **All three attacks combined** |
| `arp-spoofing` | ARP spoofing attack (development branch) |
| `dns-hijacking` | DNS man-in-the-middle attack (development branch) |
| `host-location-hijacking` | Host-location hijacking attack (development branch) |

---

## Testbed

All three attacks share **one reproducible testbed** so results can be compared directly: same topology, same controller version, same OpenFlow version. The environment is scripted and version-pinned, so a result can be reproduced on another machine.

| Component | Role |
|-----------|------|
| **Mininet** | Emulates the hosts, switches, links, and the router |
| **ONOS 2.7.0** | SDN controller (topology discovery, host tracking, reactive forwarding) |
| **Open vSwitch** | OpenFlow data-plane switches `s1`, `s2`, `s3` |
| **Linux router `r1`** | Layer-3 gateway between the three subnets |
| **OpenFlow 1.3** | Southbound control protocol (controller ↔ switches) |


The attacker is simply one of the hosts on the victim's LAN; it needs no privilege beyond being attached to a switch (except Attack 2, which additionally needs ONOS REST credentials). Switches pin **OpenFlow 1.3** (`protocols='OpenFlow13'`) or ONOS will not keep them connected.

---

## Requirements & Setup

Run on a Linux host with a real kernel — the official Mininet VM, an Ubuntu VM, or WSL2 (Ubuntu). Do **not** use an unprivileged container or Codespace: the Open vSwitch datapath cannot forward packets there and `pingall` drops 100%.

```bash
# Verify Mininet/OVS can forward
sudo mn --test pingall --topo single,3        # must print "Results: 0% dropped"

# Core tools
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch python3-scapy \
                        dnsmasq dnsutils tcpdump iperf3 hping3 curl docker.io
sudo service openvswitch-switch start
sudo service docker start

# ONOS 2.7.0 as a Docker container
sudo docker run -d --name onos \
  -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
  onosproject/onos:2.7.0
sleep 90   # ONOS takes ~60–90s to boot
```

Each attack's run guide lists the exact ONOS apps to activate (`org.onosproject.openflow`, `fwd`, `hostprovider`, `lldpprovider`) and the credentials it uses.

---

## Running the Attacks

Each attack has a dedicated, tested run guide — start there. The summaries below are orientation only.

### Attack 1 - ARP Spoofing → [`arp-spoofing/RUN.md`](arp-spoofing/RUN.md)

ARP has no authentication: a host overwrites its cache from any reply, even unsolicited ones. A Scapy script on the attacker sends two forged replies every two seconds (h1 told h2 is at the attacker's MAC, and vice versa) with IP forwarding on, so the attacker silently relays traffic. Because ONOS also learns hosts from ARP, the same replies poison the controller's host table.

```bash
cd arp-spoofing
sudo mn -c && sudo python3 arp_topo.py        # Terminal A → mininet>
# inside mininet:
atk sysctl -w net.ipv4.ip_forward=1
atk python3 arp_attack.py &
```

**Verify:** `h1 arp -n` / `h2 arp -n` show the attacker's MAC (`…:01`) for each other's IP; `hosts` in ONOS shows that one MAC owning all three IPs; TTL drops 64→63 (one extra hop).

### Attack 2 - DNS Man-in-the-Middle → [`dns-hijacking/RUN.md`](dns-hijacking/RUN.md)

The attacker installs **two OpenFlow 1.3 flows on `s1` through the ONOS northbound REST API** (appId `org.sdnproject.dnshijack`, priority 50000, permanent). The *outbound* rule rewrites the victim's UDP/53 query to the attacker; the *return* rule re-sources the proxy's reply as the real resolver (10.0.30.10) so the victim's OS accepts it transparently. The attacker runs a dnsmasq **proxy** that forwards each query to the real server and relays the genuine answer — a true MitM — while altering one record in flight.

```bash
cd dns-hijacking
sudo python3 dns_topo.py                       # Terminal A → mininet>
python3 scripts/push_dns_hijack.py             # Terminal B — install flows via ONOS
# ... run the demo queries from RUN.md ...
python3 scripts/remove_dns_hijack.py           # clean up (HTTP 204)
```

**Verify:** `intranet.lab.example` still resolves to the real `10.0.30.90` but relayed through the attacker, while `www.lab.example` is altered to `10.6.6.66`. The **real server's log** shows the query arriving from the attacker (10.0.10.13), not the victim - the fingerprint that distinguishes a MitM from a redirect.

### Attack 3 - Host-Location Hijacking → [`host-location-hijacking/README.md`](host-location-hijacking/README.md)

ONOS fills its host-tracking table from the source addresses of packets it sees, without verifying them. The attacker (on the victim's switch `s1`) sends a packet whose source MAC is the victim's, so ONOS believes the victim moved to the attacker's port and delivers the victim's traffic there. The attacker also adopts the victim's MAC/IP to receive and answer that traffic — a full MitM.

```bash
cd host-location-hijacking
sudo mn -c && sudo python3 hlh_topo.py         # Terminal A → mininet>
# inside mininet:
xterm atk        # in the pop-up:  python3 hlh_mitm.py
```

**Verify:** `hosts | grep 10.0.10.11` in ONOS shows the victim's entry move to the attacker's port (s1, port 4); `srv ping 10.0.10.11` has 0% loss but the echoes appear in the **attacker's** capture (TTL 63), while the **real victim's** capture stays empty.

> Placement matters: when the attacker was moved to a *different* switch (behind the router), the host table was still fully poisoned but interception was **0%**  the controller had no forwarding path to deliver the victim's traffic to the attacker. The decisive factor is whether the attacker sits in the victim's forwarding path, not merely poisoning the controller.

---

## Measured Results

All numbers below are from the project testbed (Mininet + ONOS 2.7.0, OpenFlow 1.3).

**Cross-attack comparison**

| Metric | ARP Spoofing | DNS Hijacking | Host-Location Hijacking |
|--------|--------------|---------------|-------------------------|
| SDN layer targeted | Host ARP cache (L2); also host table | Control-plane flow table (ONOS REST API) | Controller host-tracking table |
| Attacker privilege | LAN host, no controller access | LAN host **+ ONOS REST credentials** | LAN host, no controller access |
| Time to success | A few seconds | **0.09 s** (two REST calls, HTTP 201) | A few seconds |
| Means | Continuous forged ARP replies | Two OpenFlow rules via the controller | Continuous forged ARP + identity spoof |
| Control-plane corruption | Host table poisoned as a side effect | Two permanent flows on the switch | Victim's host entry relocated to the attacker |
| Interception | 100% (bidirectional) | 100% (20/20 DNS queries) | 100% (full MitM; real victim 0%) |
| Detectable where | **Easiest** — noisy ARP stream on the data plane | **Hardest** — control plane only (unexpected flows + resolver log) | Moderate — host-table change + victim goes silent |
| Recovery | Self-corrects after the attack stops | Instant on flow delete (HTTP 204) | Automatic re-learn after the attack stops |

**Selected per-attack metrics**

- **ARP:** RTT ≈4.1 ms → ≈4.8 ms under attack; TTL 64→63; two forged replies per 2-second cycle.
- **DNS:** flow install 0.090 s; 22 packets carried per flow during the test; controller cost 0.66% CPU / 931.6 MiB RAM (no `PACKET_IN` storm); 20/20 queries steered.
- **Host-location:** TTL 64→63; one forged frame per 2 s (negligible controller cost); 5/5 server→victim pings delivered to the attacker, 0 to the real victim.

---

## Authors

- **Chiamaka Nwaoyibo**
- **Divya Ravichandran**
- **Fathima Sheema Mohamed Ruzaik**
- **Vo-Truc-Ngan Dinh**

Course project for *Security of Software-Defined Networking*.

---

<div align="center">

*Educational material demonstrating SDN attack mechanics for learning and defensive purposes only.*

</div>
