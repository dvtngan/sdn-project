# M3 — Attack 2: DNS Man-in-the-Middle via OpenFlow Rule Insertion (ONOS Control Plane)

**Project:** Implementation and Analysis of Man-in-the-Middle Attacks in SDN (Group 5)
**Work package:** M3 — Attack 2 (DNS man-in-the-middle, control-plane)
**Author:** Fathima Sheema Mohamed Ruzaik — 025500264A
**Testbed:** Mininet + **ONOS 2.7.0** + Open vSwitch, **OpenFlow 1.3** (the full M1 testbed)
**Status:** Completed — attack implemented through the ONOS controller, verified with resolver logs, and measured

> **Scope / ethics note.** This is a self-contained virtual lab built with Mininet.
> Every host, switch, resolver, and intercepted query exists only inside the
> emulated network and is destroyed on teardown. No real DNS, host, or network was
> targeted. The work is for academic study only, per the project proposal.

---

## 1. Objective

Demonstrate Attack 2 from the proposal as a **true man-in-the-middle** on the DNS
resolution path: place the attacker *on the path* between the victim and the
**real** DNS server **by installing OpenFlow rules at the switch through the SDN
controller (ONOS)**, so the attacker reads and can alter the victim's DNS while
the real server still answers and neither side detects the interception.

The SDN-specific point is the *method*. Instead of racing spoofed DNS replies on
the LAN, the attacker abuses the **programmability of the control plane**: it uses
ONOS's northbound REST API to install two OpenFlow 1.3 flow rules on the victim's
switch that steer all UDP/53 traffic through the attacker and re-source the reply
so it appears to come from the legitimate resolver.

The distinction from a plain *redirect* is deliberate and is the core of this
work: the attacker does **not** merely impersonate the server with a rogue
resolver. It runs a **DNS proxy** that forwards each query to the genuine resolver
and relays the real answer back — a genuine man-in-the-middle — and alters a chosen
record in flight to show it can both read and modify the traffic.

The three proposal questions this work-package answers:

1. **How easy is it to conduct?** — attacker position, privileges, tools, time.
2. **What part of SDN does it target?** — the control-plane flow table (ONOS-owned flows on `s1`).
3. **What are the consequences?** — interception completeness, transparency, latency, controller cost, recovery.

---

## 2. Testbed

Emulated in Mininet with the OVS **kernel** datapath, switches pinned to
**OpenFlow 1.3**, controlled by **ONOS 2.7.0** (Docker container). The topology
(`dns_topo.py`) builds three LANs joined by a router `r1`:

```
 LAN A 10.0.10.0/24                     Server LAN 10.0.30.0/24
 ┌─────────────────┐
 │ h1  10.0.10.11  │ victim
 │ h2  10.0.10.12  │                    ┌──────────────────────┐
 │ h3  10.0.10.13  │ ATTACKER (DNS      │ srv 10.0.30.10        │ real DNS
 └───────┬─────────┘        proxy/MITM) │   www.lab.example     │ = 10.0.30.80
         │                              │   intranet.lab.example│ = 10.0.30.90
        s1 ── r1 ── s3 ─────────────────┤                       │
         │                              └──────────────────────┘
      ONOS 2.7.0 controller @ 127.0.0.1:6653  (OpenFlow 1.3)
```

ONOS registered all three switches over OpenFlow 1.3 and `pingall` returned
`0% dropped (42/42 received)`, confirming the testbed and router are live.

Fixed `s1` port layout (set by link order in `dns_topo.py`):

| Port | Host |
|------|------|
| `s1-eth1` | h1 (victim) |
| `s1-eth3` | h3 (attacker / DNS proxy) |
| `s1-eth4` | r1 (LAN A gateway) |

The attack script discovers the victim/attacker switch, ports and MAC
**automatically from ONOS's host database** (run `pingall` first), so no values
are hand-copied.

### Two resolvers (dnsmasq)

| Resolver | Host | Listens on | Behaviour |
|----------|------|-----------|-----------|
| **Legit** (`dnsmasq-legit.conf`) | srv | `10.0.30.10:53` | real answers: `www.lab.example`→`10.0.30.80`, `intranet.lab.example`→`10.0.30.90` |
| **Proxy** (`dnsmasq-proxy.conf`) | h3 (attacker) | `10.0.10.13:53` | **forwards every query to the real server** (`server=10.0.30.10`); **alters one record** in flight: `www.lab.example`→`10.6.6.66` |

The two lab names serve different proof roles: `intranet.lab.example` is **relayed**
untouched (proves the real server stays in the loop), and `www.lab.example` is
**altered** (proves in-flight modification).

---

## 3. Attack mechanism

Two OpenFlow 1.3 flow rules are installed on `s1` **through ONOS's REST API**
(`POST /onos/v1/flows/{deviceId}`), tagged with application id
`org.sdnproject.dnshijack`, at **priority 50000** (above ONOS's reactive
forwarding) and `isPermanent: true`:

- **OUTBOUND** — the victim's DNS query to the real resolver is steered to the
  attacker (destination MAC + IP rewritten to h3), delivering it to the proxy:
  ```
  match : eth_type=0x0800, ip_proto=17(UDP), ip_src=10.0.10.11,
          ip_dst=10.0.30.10, udp_dst=53
  action: set eth_dst=00:00:00:00:00:04, set ip_dst=10.0.10.13, output port 3
  ```
- **RETURN** — the proxy's reply is re-sourced as the real resolver, so the victim
  accepts it transparently:
  ```
  match : eth_type=0x0800, ip_proto=17(UDP), ip_src=10.0.10.13,
          ip_dst=10.0.10.11, udp_src=53
  action: set ip_src=10.0.30.10, output port 1
  ```

With the flows in place the victim's query reaches the attacker's proxy on
`10.0.10.13:53`. The proxy then acts as a man-in-the-middle:

- for `intranet.lab.example` it **forwards** the query to the real server
  `10.0.30.10`, receives `10.0.30.90`, and relays it back to the victim;
- for `www.lab.example` it answers locally with `10.6.6.66`, **altering** the record.

The victim sent its query to `10.0.30.10` and receives a reply that appears to come
from `10.0.30.10` (the RETURN flow re-sources it), so it detects nothing. Only
UDP/53 is affected; all other traffic forwards normally.

### Why it is a man-in-the-middle and not a redirect (key finding)

Because the attacker **forwards to and relays from the genuine resolver**, the real
server remains part of every exchange — the defining property of a man-in-the-middle.
This was proven directly from the resolver logs (Section 4, Step 6): during the
attack the real server received the `intranet` query **from the attacker's address
`10.0.10.13`**, not from the victim. A rogue-resolver redirect could never produce
that evidence, because the real server would never be contacted at all.

### Why the attack must go through the controller

Flows inserted directly with `ovs-ofctl` do not survive under ONOS: the controller
reconciles each switch's flow table and purges any rule it did not install. A
durable flow-based attack must therefore be driven **through** the control plane —
the REST-API method makes ONOS the owner of the malicious flows, so the controller
actively maintains them. (The `ovs-ofctl` scripts remain valid as a standalone-switch
cross-check, where no controller is present to purge them.)

---

## 4. Procedure and commands (as executed)

### Step 1–2 — Start ONOS and the testbed

```bash
sudo docker run -d --name onos -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 onosproject/onos:2.7.0
# activate org.onosproject.openflow and org.onosproject.fwd
cd ~/sdn-project/dns-hijacking && sudo python3 dns_topo.py   # banner: controller: ONOS @ 127.0.0.1:6653
```
```
mininet> pingall
*** Results: 0% dropped (42/42 received)
```

### Step 3 — Start both resolvers

```
mininet> srv dnsmasq --conf-file=$PWD/scripts/dnsmasq-legit.conf
mininet> h3  dnsmasq --conf-file=$PWD/scripts/dnsmasq-proxy.conf
```
`ss -lunp` confirmed `srv` listening on `10.0.30.10:53` and `h3` on `10.0.10.13:53`.

### Step 4 — Baseline (attack OFF)

```
mininet> h1 dig +short @10.0.30.10 www.lab.example        -> 10.0.30.80
mininet> h1 dig +short @10.0.30.10 intranet.lab.example   -> 10.0.30.90
```
Both honest answers come straight from the real server — the baseline.

### Step 5 — Install the MITM flows through ONOS (attack ON)

```bash
cd ~/sdn-project/dns-hijacking/scripts
python3 push_dns_hijack.py --dry-run   # victim of:0..01 port 1; attacker of:0..01 port 3
python3 push_dns_hijack.py
```
```
[+] installed OUTBOUND hijack: HTTP 201
[+] installed RETURN rewrite:  HTTP 201
```

> Implementation note: ONOS 2.7 expects the IP in a `set-field` (L3 modification)
> action as a bare host address (`10.0.10.13`), **not** a prefix (`10.0.10.13/32`);
> the `/32` is valid only in the match criteria. Sending the prefix returned
> `HTTP 400 Bad Request`; using the bare address, both flows returned `HTTP 201`.

### Step 6 — Confirm the man-in-the-middle

Victim-visible results:
```
mininet> h1 dig +short @10.0.30.10 intranet.lab.example   -> 10.0.30.90   (relayed, real answer)
mininet> h1 dig +short @10.0.30.10 www.lab.example        -> 10.6.6.66    (altered by attacker)
```

**The real server's log (`srv /tmp/srv_dns.log`) — proof it stayed in the loop:**
```
... query[A] intranet.lab.example from 10.0.10.11   # BEFORE attack: victim asks directly
... query[A] intranet.lab.example from 10.0.10.13   # DURING attack: the ATTACKER asks on its behalf
... config  intranet.lab.example is 10.0.30.90
```
The identical query that came from the victim `10.0.10.11` before the attack
arrives from the attacker `10.0.10.13` during it — the real server answered the
man-in-the-middle. Crucially, `www.lab.example` is **absent** from the server log
during the attack: that name was altered by the attacker and never forwarded.

**The attacker's log (`h3 /tmp/h3_dns.log`) — the relay and the tamper:**
```
... query     intranet.lab.example from 10.0.10.11    # received from the victim
... forwarded intranet.lab.example to 10.0.30.10      # passed to the REAL server
... reply     intranet.lab.example is 10.0.30.90      # real answer received
... config    www.lab.example is 10.6.6.66            # this one faked locally
```

### Step 7 — Control-plane evidence

```bash
curl -u onos:rocks ".../flows/application/org.sdnproject.dnshijack" | python3 -m json.tool
# both flows: "state": "ADDED", "packets": 22, "appId": "org.sdnproject.dnshijack"
```
Both ONOS-owned flows are `ADDED` and live in the data plane, each having carried
22 packets (`ovs-ofctl dump-flows s1` confirmed the same `n_packets=22`).

### Step 8 — Teardown / recovery

```bash
python3 remove_dns_hijack.py     # HTTP 204 — flows deleted by appId
```
Resolution returns to the honest answers the instant ONOS removes the flows — the
attack is cleanly reversible.

---

## 5. Results — evaluation metrics

### How easy to conduct

| Metric | Result |
|--------|--------|
| Attacker prerequisites | A host on the LAN (h3) + reachability to the controller's northbound REST API |
| Privileges | Valid ONOS REST credentials (`onos:rocks` default) — control-plane access |
| Tools | ONOS REST API (`push_dns_hijack.py`), `dnsmasq` (proxy) |
| Time to compromise | **0.090 s** (measured, `time python3 push_dns_hijack.py`) — two REST calls, both `HTTP 201` |
| Attack success rate | **20/20 = 100%** (tampered name returned `10.6.6.66` every time) |

### What it targets

| Metric | Result |
|--------|--------|
| SDN component abused | Control-plane **flow table on `s1`**, via the ONOS northbound REST API |
| Trust assumption exploited | The controller installs and *maintains* attacker-supplied flows (priority 50000, permanent) and purges competing rules, keeping the interception stable |
| Control-plane corruption | Two false flows **owned by ONOS** (`appId=org.sdnproject.dnshijack`, `state=ADDED`), live in the data plane (`packets=22` each); removed only by explicit REST delete (`HTTP 204`) |

### Consequences

| Metric | Attack OFF | Attack ON |
|--------|-----------|-----------|
| `intranet.lab.example` resolves to | `10.0.30.90` (direct) | `10.0.30.90` — **relayed through the attacker** (real server queried from `10.0.10.13`) |
| `www.lab.example` resolves to | `10.0.30.80` | `10.6.6.66` — **altered in flight** |
| Real server in the loop | — | **Yes** — its log shows the attacker (`10.0.10.13`) as the client |
| Interception completeness | 0 / 20 | **20 / 20 (100%)** of the victim's DNS steered through the attacker |
| Victim-side change required | — | **None** — reply appears to come from `10.0.30.10` |
| DNS query latency | ~baseline | relayed name **4 ms** (extra victim→attacker→server→attacker→victim path); altered name **0 ms** (answered at the attacker) |
| Controller cost (CPU / RAM) | baseline idle | **0.66% CPU / 931.6 MiB (5.99%)** — no DoS |
| Recovery | — | Instant on flow removal (`remove_dns_hijack.py`, `HTTP 204`) |

> The latency split is itself evidence of the mechanism: the **relayed** name is
> slower because it genuinely round-trips to the real server through the attacker,
> while the **altered** name is answered locally at the attacker in ~0 ms.

### Consolidated metrics table (Attack 2 — the eight required measures)

Every value below is from the verified run captured in the screenshots of Section 4.

| Metric | Measured result | Evidence |
|--------|-----------------|----------|
| **Time taken for attack** | **0.090 s** — two REST calls, both `HTTP 201` | `time python3 push_dns_hijack.py` (Step 5) |
| **Number of packets** | **22 packets per flow** (2 flows) carried through the malicious rules | ONOS flow JSON `"packets": 22`; `ovs-ofctl dump-flows s1` `n_packets=22` (Step 7) |
| **Detectable where** | Invisible at the victim and on the data plane; visible only in the **control plane** (two unexpected high-priority flows on `s1`) and in the **real resolver's log** (query source = attacker `10.0.10.13`). See analysis below. | ONOS flows API; `srv /tmp/srv_dns.log` |
| **Success rate** | **20 / 20 = 100%** (tampered name returned `10.6.6.66` on every query) | 20-query loop (Step 6); all answers intercepted |
| **Control-plane corruption** | **2 false flows owned by ONOS** — `appId=org.sdnproject.dnshijack`, `priority 50000`, `isPermanent`, `state=ADDED`; persist until an explicit REST delete | ONOS flows API (Step 7) |
| **Consequences** | Full DNS MITM: `intranet.lab.example` **relayed** from the real server (`10.0.30.90`), `www.lab.example` **altered** in flight (`10.0.30.80`→`10.6.6.66`); **zero** victim-side change; real server proven in the loop | dig results + resolver logs (Step 6) |
| **Controller cost** | **0.66% CPU / 931.6 MiB (5.99% RAM)** — negligible, no DoS, no Packet-In storm | `docker stats onos --no-stream` (Step 7) |
| **Recovery** | **Instant** — resolution returns to honest answers the moment the flows are deleted (`HTTP 204`) | `remove_dns_hijack.py`; post-removal dig = `10.0.30.80` / `10.0.30.90` (Step 8) |

### Detectable where — where this attack can and cannot be seen

This is one of the required measures and the most revealing: the attack is deliberately
placed where the usual DNS defences do not look.

- **At the victim host — undetectable.** The victim sends its query to the correct
  resolver address (`10.0.30.10`) and receives a well-formed reply that *appears to
  come from* `10.0.30.10` (the RETURN flow re-sources it). There is no NXDOMAIN, no
  timeout, no second answer racing the first, and no change to the victim's resolver
  configuration — so classic client-side spoofing indicators are all absent.
- **On the data plane / LAN — effectively undetectable.** There is no ARP storm and
  no duplicate-reply signature that an IDS watching the wire would flag, because the
  interception is done by the switch rewriting headers, not by a second host shouting
  spoofed packets. Traffic volume and timing look almost normal (only a few ms of
  extra latency on relayed names).
- **In the control plane — this is where it shows.** The attack is visible to anyone
  who audits the switch's flow table or the controller's flow API: two unexpected,
  high-priority (50000), permanent flows on `s1` matching `udp_dst=53` with
  set-field rewrites of DNS traffic. This is the correct detection point for an
  SDN-era DNS attack — flow-table auditing, not packet inspection.
- **In the resolver's own logs — the MITM fingerprint.** The real server logs the
  `intranet` query arriving from the **attacker's** address `10.0.10.13` instead of
  the victim `10.0.10.11`. A server-side analyst correlating query source addresses
  against the expected client population would see one host resolving on behalf of
  another — the signature of a man-in-the-middle relay.

**Takeaway for detection:** this attack moves DNS interception off the host and off
the wire and into *controller state*, so it defeats endpoint and IDS-based DNS
monitoring and is caught only by **control-plane integrity monitoring** (flow-table
auditing / controller-flow provenance) and **resolver-side query-source analysis**.

---

## 6. Analysis

**Headline finding.** Using the ONOS northbound REST API, an attacker installs two
controller-owned OpenFlow rules on the victim's switch and inserts itself as a
**true man-in-the-middle** on the DNS path: it reads **100%** of the victim's DNS,
relays queries to and answers from the **real** resolver, and alters a chosen
record in flight — while re-sourcing replies so the victim detects nothing. The
interception is realised as **controller-maintained flow-table state**, not a
per-host trick — exactly the control-plane corruption the proposal set out to
demonstrate for M3.

- **It is a man-in-the-middle, proven by the server's own log.** During the attack
  the real server received the `intranet` query from the attacker's address, and
  answered it; the attacker relayed that genuine answer to the victim. The real
  server stayed in the loop — the property that separates a man-in-the-middle from
  a mere redirect — and the attacker simultaneously demonstrated it can alter a
  different record (`www`→`10.6.6.66`).
- **The control plane is the leverage point.** ONOS trusts an authenticated REST
  client and installs whatever flows it is given, at any priority. Reaching that
  northbound interface is enough to reprogram forwarding for the whole switch and
  route a victim's traffic through an attacker. The centralisation that makes SDN
  manageable makes the controller a single, high-value corruption target.
- **The controller actively protects the attack.** ONOS reconciliation purges
  rules it did not install, so a naïve `ovs-ofctl` injection is wiped out, but a
  flow installed *through* ONOS is maintained by ONOS. The defender's consistency
  mechanism becomes the attacker's persistence mechanism.
- **Stealth, not noise.** Controller cost stayed at ~0.7% CPU with no Packet-In
  storm, and the victim queries the correct resolver IP and receives a reply that
  appears to come from it. The only subtle artefact is a few milliseconds of added
  latency on relayed names.
- **Total but reversible.** Impact while active is complete (100% of the victim's
  DNS traverses the attacker), yet the attack is removed instantly by deleting the
  flows — which is why it is hard to detect from the data plane alone.

**Which SDN layer is exposed (M3's contribution to the final comparison):** the
**control plane — the controller's northbound interface and flow table.** Any
credentialed or unauthenticated path to the controller's programming API lets an
attacker turn forwarding policy itself into a man-in-the-middle, network-wide.

---

## 7. Deliverables (M3 checklist)

| Proposal deliverable (M3) | Provided |
|---------------------------|----------|
| OpenFlow rule-insertion method | **`scripts/push_dns_hijack.py` / `remove_dns_hijack.py`** — install/remove via the **ONOS REST API** (primary). `scripts/dns_hijack.sh` / `dns_restore.sh` (`ovs-ofctl`) as standalone cross-check. |
| dnsmasq config | `scripts/dnsmasq-legit.conf` (real resolver, srv), `scripts/dnsmasq-proxy.conf` (attacker proxy that forwards + alters) |
| Metrics | Section 5 — 100% interception, man-in-the-middle proven from resolver logs, relayed vs altered latency, controller cost (0.66% CPU), instant recovery |
| Reproducible run guide | `RUN.md` + this report |

**Files**

```
dns-hijacking/
├── dns_topo.py                     # topology (writes /tmp/dns_hijack_env.sh)
├── RUN.md                          # step-by-step run guide
├── REPORT_M3_DNS_MITM.md           # this report
└── scripts/
    ├── dnsmasq-legit.conf          # real resolver (srv): www->10.0.30.80, intranet->10.0.30.90
    ├── dnsmasq-proxy.conf          # attacker proxy (h3): forwards to srv, alters www->10.6.6.66
    ├── push_dns_hijack.py          # PRIMARY: install MITM flows via ONOS REST API
    ├── remove_dns_hijack.py        # PRIMARY: remove flows via ONOS REST API
    ├── dns_hijack.sh               # cross-check: install via ovs-ofctl (standalone only)
    └── dns_restore.sh              # cross-check: remove via ovs-ofctl
```

---

## 8. Conclusion

M3 is complete on the full M1 testbed (Mininet + ONOS 2.7.0 + OpenFlow 1.3).
Attack 2 was implemented by driving the **ONOS controller** to install two
OpenFlow flow rules on switch `s1` via its REST API, placing the attacker as a
**true man-in-the-middle** on the victim's DNS path. The victim's DNS was steered
through the attacker's proxy with a **100% success rate** and **zero victim-side
change**; the real server was proven to remain in the loop (its log recorded the
query arriving from the attacker `10.0.10.13`), while the attacker simultaneously
**altered** a chosen record (`www.lab.example`→`10.6.6.66`). The false rules were
shown to be **owned and maintained by ONOS** (`appId=org.sdnproject.dnshijack`,
priority 50000, permanent) and live in the data plane (`packets=22` each); the
controller incurred negligible cost (~0.7% CPU, no DoS); and resolution recovered
instantly on teardown (`HTTP 204`). This demonstrates that in an OpenFlow SDN the
controller's flow table and northbound interface are a direct, high-impact, and
stealthy man-in-the-middle surface on the DNS resolution path.
