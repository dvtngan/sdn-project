# Attack 2 — DNS Hijacking via OpenFlow Rule Insertion

## Overview

The attacker steers the victim's DNS traffic (UDP/53) to an attacker-controlled
resolver by **installing OpenFlow 1.3 rules on the switch through the ONOS
controller**. This is the method the proposal requires (M3: "OpenFlow rule
insertion method, dnsmasq config, metrics"), and it exercises the full M1 testbed
(Mininet + ONOS + OpenFlow 1.3).

```
 h1 (victim   10.0.10.11) --\
 h2           10.0.10.12 ----+-- s1 --- r1 --- s3 --- srv (legit DNS 10.0.30.10)
 h3 (attacker 10.0.10.13) --/        ONOS controller @ 127.0.0.1:6653

 Normal : h1 queries 10.0.30.10 -> www.lab.example = 10.0.30.80  (real)
 Attack : ONOS-installed flows on s1 steer h1's UDP/53 to h3
                                  -> www.lab.example = 10.6.6.66  (attacker)
```

Two flows are installed on `s1` at priority 50000 (above ONOS's reactive
forwarding) and marked permanent:

- **Outbound**: `ip_src=h1, udp, ip_dst=10.0.30.10, udp_dst=53` → rewrite dst MAC/IP to h3, output to h3.
- **Return**: `ip_src=h3, udp, ip_dst=h1, udp_src=53` → rewrite src IP back to 10.0.30.10, output to h1.

The victim queries the *legit* resolver address but silently gets the *attacker's*
answer, and the reply looks like it came from the legit resolver.

### Two methods, and why the controller one is used

| Method | Script | Notes |
|--------|--------|-------|
| **ONOS REST API** (primary) | `push_dns_hijack.py` / `remove_dns_hijack.py` | The controller installs and *owns* the flows. This is the method to use with ONOS. |
| `ovs-ofctl` direct (fallback) | `dns_hijack.sh` / `dns_restore.sh` | Inserts flows straight onto the switch. **Only works without a controller** — see note below. |

> **Important:** when ONOS is running, flows inserted directly with `ovs-ofctl`
> are removed within seconds, because ONOS reconciles the flow table and purges
> any rule it did not install. The `ovs-ofctl` scripts therefore work only in
> standalone mode (no controller). With ONOS, use `push_dns_hijack.py`.

## Files

| File | Purpose |
|------|---------|
| `dns_topo.py` | Mininet topology (OVS kernel datapath, OF1.3). Connects to ONOS, or runs standalone with `DNS_STANDALONE=1`. Writes `/tmp/dns_hijack_env.sh`. |
| `scripts/dnsmasq-legit.conf` | legitimate resolver config (host `srv`) |
| `scripts/dnsmasq-rogue.conf` | attacker resolver config (host `h3`) |
| `scripts/push_dns_hijack.py` | installs the hijack flows via the ONOS REST API |
| `scripts/remove_dns_hijack.py` | removes them via the ONOS REST API |
| `scripts/dns_hijack.sh` | fallback: installs the flows with `ovs-ofctl` (standalone only) |
| `scripts/dns_restore.sh` | fallback: removes the `ovs-ofctl` flows |

---

## Requirements

Run on a Linux host with a real kernel — the official Mininet VM, any Ubuntu VM,
or WSL2 (Ubuntu). Do **not** use an unprivileged container / GitHub Codespace:
there the Open vSwitch datapath cannot forward packets and `pingall` drops 100%.

Verify the environment forwards packets before going further:

```bash
sudo mn --test pingall --topo single,3
# must print "Results: 0% dropped".
```

Install the required packages:

```bash
sudo apt-get update
sudo apt-get install -y openvswitch-switch dnsmasq dnsutils tcpdump iperf3 curl
sudo service openvswitch-switch start
# dnsmasq is launched per-host from the Mininet CLI, so stop any system instance:
sudo service dnsmasq stop 2>/dev/null || true
```

ONOS runs as a Docker container, so Docker is also needed:

```bash
sudo apt-get install -y docker.io
sudo service docker start
sudo docker run --rm hello-world     # prints "Hello from Docker!" if working
```

---

## Procedure

### Step 1 — Start ONOS

```bash
sudo docker run -d --name onos \
  -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
  onosproject/onos:2.7.0
sleep 90     # ONOS takes ~60-90s to boot

# activate the OpenFlow providers and reactive forwarding
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
```

### Step 2 — Start the testbed

```bash
cd dns-hijacking
sudo python3 dns_topo.py
```

The banner should read `controller: ONOS @ 127.0.0.1:6653`. At the `mininet>`
prompt, learn every host:

```
mininet> pingall
```

`0% dropped` confirms the testbed (and the router) are up. Confirm ONOS has
registered the three switches over OpenFlow 1.3:

```bash
curl -u onos:rocks http://localhost:8181/onos/v1/devices | python3 -m json.tool
# s1, s2, s3 with "protocol": "OF_13", "available": true
```

### Step 3 — Start the two resolvers

```
mininet> srv dnsmasq --conf-file=$PWD/scripts/dnsmasq-legit.conf
mininet> h3  dnsmasq --conf-file=$PWD/scripts/dnsmasq-rogue.conf
mininet> srv ss -lunp | grep :53
mininet> h3  ss -lunp | grep :53
```

Each `ss` line should show the resolver listening on its address and port 53.

### Step 4 — Baseline (attack OFF)

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.0.30.80
```

`10.0.30.80` is the honest answer — the baseline.

### Step 5 — Install the hijack flows (attack ON)

In a second terminal (the Mininet CLI stays open):

```bash
cd dns-hijacking/scripts
python3 push_dns_hijack.py --dry-run     # verify host discovery from ONOS
python3 push_dns_hijack.py               # install via the ONOS REST API
```

Both flows should return `HTTP 201`. The script reads the victim/attacker switch,
ports and MAC from ONOS's host database, so `pingall` in Step 2 must have run
first.

### Step 6 — Confirm the hijack

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.6.6.66
```

`10.6.6.66` is the attacker's answer. The answer flips `10.0.30.80` → `10.6.6.66`
with no change on the victim = successful hijack. Confirm ONOS owns the flows and
that they are live on the switch:

```bash
curl -u onos:rocks "http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack" | python3 -m json.tool
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep -E 'tp_dst=53|tp_src=53'
```

### Step 7 — Teardown

```bash
python3 remove_dns_hijack.py
```
```
mininet> h1 dig +short @10.0.30.10 www.lab.example   # 10.0.30.80 again
mininet> exit
```
```bash
sudo mn -c
sudo docker rm -f onos
```

---

## Evaluation (metrics for the report)

Record each metric twice — attack OFF (baseline) and attack ON.

**How easy to conduct**
- Attacker prerequisites: a host on the LAN + reachability to the controller's REST API.
- Time to compromise: two REST calls (`push_dns_hijack.py`), both sub-second.
- Success rate — 20 queries, count attacker answers:
  ```
  mininet> h1 bash -c 'for i in $(seq 20); do dig +short @10.0.30.10 www.lab.example; done'
  ```

**What it targets**
- SDN component abused: the control-plane flow table on `s1`, via ONOS's northbound API.
- Control-plane corruption — the false flows and how long they persist:
  ```bash
  curl -u onos:rocks "http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack" | python3 -m json.tool
  ```

**Consequences**
- Interception completeness: fraction of the 20 answers that are `10.6.6.66`.
- Latency: `mininet> h1 ping -c 20 10.0.30.10`, attack off vs on.
- Throughput: `iperf3` between two hosts, attack off vs on.
- Controller cost: CPU / memory during the attack:
  ```bash
  sudo docker stats onos --no-stream
  ```

---

## Standalone mode (no ONOS)

If ONOS or Docker is not available, the topology can run the switches as plain L2
learning switches, and the hijack is installed directly with `ovs-ofctl`:

```bash
sudo DNS_STANDALONE=1 python3 dns_topo.py     # no controller
# ... pingall, start resolvers, baseline (Steps 2-4 above) ...

cd scripts
sudo bash dns_hijack.sh         # install flows with ovs-ofctl
# ... confirm 10.6.6.66 ...
sudo bash dns_restore.sh        # remove them
```

This produces the same hijack at the data plane. Note it as the fallback
controller mode in the report. (The `ovs-ofctl` scripts read their values from
`/tmp/dns_hijack_env.sh`, which `dns_topo.py` writes on startup.)

---

## Troubleshooting

- **`pingall` drops 100%** → the environment is a container/Codespace, not a real
  kernel. Use a VM or WSL2. Confirm with `sudo mn --test pingall --topo single,3`.
- **`push_dns_hijack.py` says "victim or attacker not found in ONOS hosts"** → run
  `pingall` in Mininet first so ONOS learns the hosts, then retry.
- **`dig` still returns `10.0.30.80` after installing with `ovs-ofctl` under ONOS**
  → ONOS has purged the directly-inserted flows. Use `push_dns_hijack.py` instead,
  or switch to `DNS_STANDALONE=1`.
- **dnsmasq "address already in use"** → a system dnsmasq holds port 53:
  `sudo service dnsmasq stop`.
- **`docker: command not found` / daemon not running** → `sudo apt-get install -y
  docker.io` then `sudo service docker start` (on WSL2, if the service fails, start
  it with `sudo dockerd > /tmp/dockerd.log 2>&1 &`).
- **`/tmp/dns_hijack_env.sh not found`** (standalone method) → start `dns_topo.py`
  first; it writes the file.
```
