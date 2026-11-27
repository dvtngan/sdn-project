# Attack 3 — Host-Location Hijacking (Man-in-the-Middle)

The attacker fools the **ONOS** controller into thinking the victim has moved to the attacker's
port, then takes on the victim's identity. Traffic meant for the victim is delivered to — and
answered by — the attacker, while the real victim is cut out. A man-in-the-middle.

The attacker sits on the **same switch as the victim (s1)**, which is what lets the controller
redirect the victim's traffic to it.

### Roles

| Role | Host | IP | Where |
|------|------|-----|-------|
| Victim | `h1` | 10.0.10.11 | s1 |
| Server (talks to the victim) | `srv` | 10.0.30.10 | s3 |
| Attacker (man in the middle) | `atk` | 10.0.10.66 | s1 |

### Files

| File | Purpose |
|------|---------|
| `hlh_topo.py` | The testbed (3 LANs + router; attacker on the victim's switch). |
| `hlh_mitm.py` | The full MITM — adopts the victim's identity and poisons continuously. |
| `hlh_attack.py` | One-shot — flips the victim's host-table entry once. |
| `hlh_attack_sustained.py` | Keeps re-poisoning (no identity change). |

### Requirements

Mininet, Open vSwitch, Scapy (`sudo apt install python3-scapy`), and ONOS 2.7.0 running in
Docker as a container named `onos`.

> You will use three terminals: the **ONOS** console, the **Mininet** CLI, and small `xterm`
> pop-up windows that run inside a host. Each step below says which one to use.

---

## Step 1 — Start ONOS  *(any terminal)*

```bash
sudo docker start onos
```

Wait about 40 seconds for it to finish starting.

## Step 2 — Log into ONOS  *(any terminal)*

```bash
ssh -p 8101 -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa onos@localhost
```

Password: `rocks` (type `yes` if asked about a fingerprint).

## Step 3 — Switch on the ONOS apps  *(ONOS console)*

```
app activate org.onosproject.openflow
```
```
app activate org.onosproject.fwd
```
```
app activate org.onosproject.lldpprovider
```

> Do **not** run `wipe-out please` — it breaks discovery and nothing will work.

## Step 4 — Start the network  *(new terminal → becomes Mininet)*

```bash
cd host-location-hijacking
```
```bash
sudo mn -c
```
```bash
sudo python3 hlh_topo.py
```

Wait for the `mininet>` prompt.

## Step 5 — Check it is healthy

**ONOS console:**
```
summary
```
> Expect `devices=3`. (`links=0` is normal here — the router joins the LANs.)

**Mininet (run twice; the first can be lossy):**
```
pingall
```
> Expect `0% dropped`.

## Step 6 — Confirm the victim's address  *(ONOS console)*

```
hosts | grep 10.0.10.11
```

> The victim `h1`'s MAC should be `00:00:00:00:00:02`, on switch s1.
> If it differs, update `VICTIM_MAC` in `hlh_mitm.py`.

## Step 7 — Launch the attack  *(Mininet)*

Open a window on the attacker:
```
xterm atk
```

Then, **inside the pop-up window**:
```bash
python3 hlh_mitm.py
```

> It prints "Adopted victim identity ..." then `poison #1, #2, ...`. Leave this window running.

## Step 8 — Confirm the hijack  *(ONOS console)*

```
hosts | grep 10.0.10.11
```

> The victim's entry now points at the **attacker's port** on s1. The host table is poisoned.

## Step 9 — Prove the interception

Open a capture window on the attacker — **Mininet:**
```
xterm atk
```
**Inside that pop-up:**
```bash
tcpdump -i atk-eth0 -n icmp
```

Open a capture window on the real victim — **Mininet:**
```
xterm h1
```
**Inside that pop-up:**
```bash
tcpdump -i h1-eth0 -n icmp
```

Now make the server talk to the victim — **Mininet:**
```
srv ping -c 5 10.0.10.11
```

> **Expected (the man-in-the-middle):**
> - `srv ping` → **0% loss** (the conversation flows).
> - **attacker** window → shows the echo **requests arriving and replies leaving**.
> - **victim** window → stays **empty** (the real victim gets nothing).

## Step 10 — Stop the attack  *(attacker pop-up)*

```
Ctrl + C
```

To reset the whole network, run `sudo mn -c` in the Mininet terminal.

---

### Optional — one-shot version (just flip the table)

**Mininet:**
```
atk python3 hlh_attack.py
```
Then check `hosts | grep 10.0.10.11` in ONOS — the entry moves to the attacker's port.

> **Note for all topologies in this project:** each switch must pin OpenFlow 1.3
> (`protocols='OpenFlow13'`), or ONOS will not keep the switches connected (`devices=0`).
