# Attack 2 — DNS Hijacking via ONOS OpenFlow Rules

## Overview

This attack targets the control plane's programmability. Rather than racing
spoofed DNS replies on the LAN, the controller (ONOS) is driven to install
OpenFlow rules on the victim's switch that steer the victim's DNS traffic
(UDP/53) to an attacker-controlled resolver, and rewrite the reply so the
victim accepts it as legitimate.

```
 h1 (victim   10.0.10.11) --\
 h2           10.0.10.12 ----+-- s1 --- r1 --- s3 --- srv (legit DNS 10.0.30.10)
 h3 (attacker 10.0.10.13) --/        ONOS controller @ 127.0.0.1:6653

 Normal : h1 queries srv  ->  www.lab.example = 10.0.30.80   (real)
 Attack : an ONOS flow on s1 steers h1's UDP/53 to h3
                            ->  www.lab.example = 10.6.6.66   (attacker)
```

## Files

| File | Purpose |
|------|---------|
| `scripts/dns_topo_userspace.py` | Mininet topology (userspace OVS datapath) |
| `scripts/dnsmasq-legit.conf` | legitimate resolver config (host `srv`) |
| `scripts/dnsmasq-rogue.conf` | attacker resolver config (host `h3`) |
| `scripts/push_dns_hijack.py` | installs the OpenFlow redirect rules via the ONOS REST API |
| `scripts/remove_dns_hijack.py` | removes the rules |

On a host that provides the OVS kernel datapath, the project topology
`dns_topo.py` may be used in place of `dns_topo_userspace.py`.

---

## Environment

Required packages: Mininet, Open vSwitch, dnsmasq, dnsutils, tcpdump, iperf3,
Python 3. ONOS 2.7 is run as a controller and reached over its REST API
(`onos:rocks`, port 8181) and OpenFlow (port 6653).

Install packages and start Open vSwitch:

```bash
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch openvswitch-common \
    dnsmasq dnsutils tcpdump iperf3 python3 curl
sudo service openvswitch-switch start
sudo systemctl disable --now dnsmasq   # free port 53; dnsmasq is launched per host
```

Start ONOS and activate the OpenFlow provider and reactive forwarding:

```bash
docker run -d --name onos -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
    onosproject/onos:2.7.0
# allow ~60-90s for ONOS to boot, then:
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
curl -u onos:rocks http://localhost:8181/onos/v1/devices        # returns JSON when ready
```

---

## Procedure

### Step 1 — Start the testbed

```bash
cd dns-hijacking/scripts
sudo python3 dns_topo_userspace.py
```

At the `mininet>` prompt, generate traffic so ONOS learns every host:

```
mininet> pingall
```

A 0% drop rate confirms the topology and router are up.

### Step 2 — Start the two resolvers

Open terminals for the server and attacker hosts:

```
mininet> xterm srv h3
```

On `srv` (legitimate resolver), using the absolute path to the config:

```bash
dnsmasq --conf-file=$(pwd)/dnsmasq-legit.conf -d
```

On `h3` (rogue resolver), left running in the foreground to log hijacked queries:

```bash
dnsmasq --conf-file=$(pwd)/dnsmasq-rogue.conf -d
```

### Step 3 — Baseline measurement (attack off)

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.0.30.80
```

`10.0.30.80` is the legitimate answer and establishes the baseline.

### Step 4 — Install the redirect rules

In a separate terminal:

```bash
cd dns-hijacking/scripts
python3 push_dns_hijack.py            # --dry-run prints the flows without installing
```

The switch, ports and attacker MAC are read from the ONOS host database, and two
flows are installed on s1: an outbound hijack (victim → real resolver is
redirected to the attacker) and a return rewrite (the attacker's reply is
re-sourced as the real resolver).

### Step 5 — Post-attack measurement (attack on)

The victim issues the same query to the same resolver address:

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.6.6.66
```

`10.6.6.66` is the attacker-chosen answer. The query also appears in the `h3`
dnsmasq log. The change from `10.0.30.80` to `10.6.6.66`, with no change on the
victim, is the evidence of a successful hijack.

The corrupted flows can be confirmed in the controller:

```bash
curl -u onos:rocks http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack
```

### Step 6 — Teardown

```bash
python3 remove_dns_hijack.py
mininet> h1 dig +short @10.0.30.10 www.lab.example   # returns 10.0.30.80 again
mininet> exit
sudo mn -c
```

---

## Evaluation

Metrics are recorded twice — attack off (baseline) and attack on — for a direct
comparison.

**How easy to conduct**
- Attacker prerequisites: a host on the LAN and REST access to the controller.
- Time to compromise: `time python3 push_dns_hijack.py`.
- Success rate: 20 repeated queries, counting attacker answers:
  ```
  mininet> h1 bash -c 'for i in $(seq 20); do dig +short @10.0.30.10 www.lab.example; done'
  ```

**What it targets**
- SDN component abused: the control-plane flow table on s1.
- Control-plane corruption: the false flows and their persistence:
  ```
  curl -u onos:rocks http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack
  ```

**Consequences**
- Interception completeness: fraction of the victim's DNS answers that are the
  attacker's IP (from the loop above).
- Latency impact: `h1 ping -c 20 10.0.30.10`, attack off vs. on.
- Throughput impact: `iperf3` between two hosts, attack off vs. on.
- Controller cost: Packet-In rate and CPU during the attack (`docker stats onos`).

---

## Notes

- `push_dns_hijack.py` reports "host not found" until each host has sent traffic;
  `pingall` resolves this.
- dnsmasq requires an absolute `--conf-file` path (`$(pwd)/...`).
- "address already in use" from dnsmasq indicates the system dnsmasq is still
  running on port 53; stop it with `sudo systemctl stop dnsmasq`.
- A switch start-up failure on the kernel datapath is cleared with `sudo mn -c`;
  `dns_topo_userspace.py` forces the userspace datapath.
