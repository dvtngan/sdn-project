# Attack 2 — DNS Hijacking via OpenFlow Rule Insertion

## Overview

The attacker steers the victim's DNS traffic (UDP/53) to an attacker-controlled
resolver by **installing OpenFlow 1.3 rules at the switch**. This is the method
the proposal requires (M3: "OpenFlow rule insertion method, dnsmasq config,
metrics"). Here the rules are inserted directly with `ovs-ofctl` — a reliable,
self-contained OpenFlow rule-insertion method — while ONOS runs as the controller
so the testbed still matches M1 (Mininet + ONOS + OpenFlow 1.3).

```
 h1 (victim   10.0.10.11) --\
 h2           10.0.10.12 ----+-- s1 --- r1 --- s3 --- srv (legit DNS 10.0.30.10)
 h3 (attacker 10.0.10.13) --/        ONOS controller @ 127.0.0.1:6653

 Normal : h1 queries 10.0.30.10 -> www.lab.example = 10.0.30.80  (real)
 Attack : OF flows on s1 steer h1's UDP/53 to h3
                                  -> www.lab.example = 10.6.6.66  (attacker)
```

Two flows are installed on s1 at priority 200 (above normal forwarding):
- **Forward**: `in_port=h1, udp, nw_dst=10.0.30.10, tp_dst=53` → rewrite dst MAC/IP to h3, output to h3.
- **Return**: `in_port=h3, udp, nw_src=10.0.10.13, tp_src=53` → rewrite src IP back to 10.0.30.10, output to h1.

So the victim queries the *legit* resolver address but silently gets the
*attacker's* answer, and the reply looks like it came from the legit resolver.

## Files

| File | Purpose |
|------|---------|
| `dns_topo.py` | Mininet topology (OVS kernel datapath, OF1.3, ONOS). Writes `/tmp/dns_hijack_env.sh`. |
| `scripts/dnsmasq-legit.conf` | legitimate resolver config (host `srv`) |
| `scripts/dnsmasq-rogue.conf` | attacker resolver config (host `h3`) |
| `scripts/dns_hijack.sh` | installs the OF1.3 redirect flows via `ovs-ofctl` |
| `scripts/dns_restore.sh` | removes the flows |

> The older `scripts/push_dns_hijack.py` / `remove_dns_hijack.py` push the same
> idea through the **ONOS REST API**. They are kept as an alternative, but the
> `ovs-ofctl` scripts above are the recommended, reliable method.

---

## ⚠️ Environment — must be a real Linux VM

**Run this on the official Mininet VM** (VirtualBox/UTM), or any Ubuntu VM with a
real kernel. **Do not run it in a GitHub Codespace / unprivileged container** —
there the Open vSwitch datapath cannot forward packets (datapath upcalls are
lost), so even a bare `sudo mn --test pingall` drops 100% and nothing works.

Sanity check your environment first:

```bash
sudo mn --test pingall --topo single,3
# must print "Results: 0% dropped". If it drops 100%, the VM/OVS is the problem,
# not these scripts.
```

Required packages (the Mininet VM already has Mininet + OVS + dnsmasq):

```bash
sudo apt-get update
sudo apt-get install -y dnsmasq dnsutils tcpdump iperf3 curl
sudo service openvswitch-switch start
# dnsmasq is launched per-host from the Mininet CLI, so stop any system one:
sudo service dnsmasq stop 2>/dev/null || true
```

### Start ONOS (controller)

If Docker is available on the VM:

```bash
docker run -d --name onos -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
    onosproject/onos:2.7.0
sleep 90   # ONOS takes ~60-90s to boot
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
curl -u onos:rocks http://localhost:8181/onos/v1/devices   # JSON when ready
```

**No ONOS? You can still run the whole attack** — start the topology with
`DNS_STANDALONE=1` (below). The switches then act as plain learning switches and
the `ovs-ofctl` hijack method is byte-for-byte identical. Note this in the report
as the fallback controller mode.

---

## Procedure

### Step 1 — Start the testbed

```bash
cd dns-hijacking
sudo python3 dns_topo.py                 # uses ONOS at 127.0.0.1:6653
# or, without ONOS:
sudo DNS_STANDALONE=1 python3 dns_topo.py
```

The script prints the s1 port numbers and the attacker MAC, and writes them to
`/tmp/dns_hijack_env.sh` for the attack script. At the `mininet>` prompt, learn
every host:

```
mininet> pingall
```

`0% dropped` confirms the testbed (and the router) are up.

### Step 2 — Start the two resolvers

```
mininet> srv dnsmasq --conf-file=$PWD/scripts/dnsmasq-legit.conf
mininet> h3  dnsmasq --conf-file=$PWD/scripts/dnsmasq-rogue.conf
mininet> srv ss -lunp | grep :53
mininet> h3  ss -lunp | grep :53
```

### Step 3 — Baseline (attack OFF)

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.0.30.80
```

`10.0.30.80` is the honest answer — the baseline.

### Step 4 — Install the hijack flows (attack ON)

In a second terminal on the VM (leave the Mininet CLI running):

```bash
cd dns-hijacking/scripts
sudo bash dns_hijack.sh            # or: sudo bash dns_hijack.sh --dry-run
```

(Equivalently, from the Mininet CLI: `mininet> sh bash scripts/dns_hijack.sh`.)

### Step 5 — Confirm the hijack

```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.6.6.66
```

`10.6.6.66` is the attacker's answer. The query also appears in `h3`'s dnsmasq
log. Answer flips `10.0.30.80` → `10.6.6.66` with **no change on the victim** =
successful hijack. Inspect the corrupted flow table:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep -E 'tp_dst=53|tp_src=53'
```

### Step 6 — Teardown

```bash
sudo bash dns_restore.sh
```
```
mininet> h1 dig +short @10.0.30.10 www.lab.example   # 10.0.30.80 again
mininet> exit
sudo mn -c
docker rm -f onos    # if you started ONOS
```

---

## Evaluation (metrics for the report)

Record each metric twice — attack OFF (baseline) and attack ON.

**How easy to conduct**
- Attacker prerequisites: a host on the LAN + the ability to insert a flow at the switch.
- Time to compromise: `time sudo bash dns_hijack.sh`.
- Success rate — 20 queries, count attacker answers:
  ```
  mininet> h1 bash -c 'for i in $(seq 20); do dig +short @10.0.30.10 www.lab.example; done'
  ```

**What it targets**
- SDN component abused: the control-plane flow table on s1.
- Control-plane corruption — the false flows and how long they persist:
  ```bash
  sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep -E 'tp_dst=53|tp_src=53'
  ```

**Consequences**
- Interception completeness: fraction of the 20 answers that are `10.6.6.66`.
- Latency: `mininet> h1 ping -c 20 10.0.30.10`, attack off vs on.
- Throughput: `iperf3` between two hosts, attack off vs on.
- Controller cost: Packet-In rate / CPU during the attack (`docker stats onos`, if ONOS is used).

---

## Troubleshooting

- **`pingall` drops 100%** → you're on a container/Codespace, not a real VM kernel.
  Move to the Mininet VM. Confirm with `sudo mn --test pingall --topo single,3`.
- **`/tmp/dns_hijack_env.sh not found`** → start `dns_topo.py` first; it writes the file.
- **dnsmasq "address already in use"** → a system dnsmasq holds port 53:
  `sudo service dnsmasq stop`.
- **dig still returns `10.0.30.80` after the attack** → run `pingall` first (so the
  router/ARP is warm), re-check the flows are present with the `dump-flows` command,
  and confirm `h3`'s dnsmasq is listening on `10.0.10.13:53`.
- **ONOS deletes the flows** → it should not (priority-200 flows it didn't create are
  left in place), but if forwarding fights the hijack, use `DNS_STANDALONE=1` to
  demonstrate the attack without ONOS.
