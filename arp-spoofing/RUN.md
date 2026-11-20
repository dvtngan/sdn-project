# Attack 1 — ARP Spoofing / Cache Poisoning (Run Guide)

This attack puts the attacker **in the middle** of two hosts on the same LAN by
sending fake ARP replies. Both victims end up sending their traffic to the
attacker, which reads it and forwards it on. It also pollutes the ONOS host
table (the SDN-specific effect).

## Files

- `arp_topo.py` — the Mininet network (3 switches, 1 router, connects to ONOS)
- `arp_attack.py` — the ARP spoofing script (run on the attacker host `atk`)

## Network and roles (LAN A = 10.0.10.0/24, switch s1)

| Host | IP          | Role      |
|------|-------------|-----------|
| h1   | 10.0.10.11  | victim 1  |
| h2   | 10.0.10.12  | victim 2  |
| atk  | 10.0.10.66  | attacker  |
| r1   | 10.0.10.1   | gateway (router) |

## Requirements

- Mininet
- ONOS running in Docker (container named `onos`)
- `scapy` and `tcpdump` installed on the machine

---

## How to run

### 1. Start ONOS and turn on the needed apps

Open the ONOS console:

```
ssh -p 8101 -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa karaf@localhost
```

(password: `karaf`). At the `karaf@root >` prompt:

```
app activate org.onosproject.openflow
app activate org.onosproject.fwd
```

Leave this window open.

### 2. Check ONOS's address and (if needed) update the topology

`arp_topo.py` connects to ONOS at `172.17.0.2` (the ONOS Docker container).
Confirm your container's address:

```
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' onos
```

If it is **not** `172.17.0.2`, edit the `RemoteController(... ip='...')` line in
`arp_topo.py` to match.

### 3. Start the network

```
sudo mn -c
sudo python3 arp_topo.py
```

Wait for the `mininet>` prompt.

### 4. Check connectivity

```
pingall
```

You want `0% dropped`.

**If pingall is NOT clean**, ONOS isn't handling ARP. In the ONOS window run:

```
app deactivate org.lab3.maccapture
app deactivate org.onosproject.hostprovider
app activate org.onosproject.hostprovider
```

Then run `pingall` again — it should be clean.

### 5. Launch the attack

In the mininet window:

```
atk sysctl -w net.ipv4.ip_forward=1
atk python3 arp_attack.py > /tmp/attack.log 2>&1 &
```

Wait ~8 seconds. (Use the full path to `arp_attack.py` if needed.)

---

## How to verify it worked

### Poisoned ARP caches (host level)

```
h1 ping -c 3 h2
h1 arp -n
h2 arp -n
```

Both victims now show the **attacker's MAC** (`00:00:00:00:00:01`) for each
other's IP — instead of the real MAC. That is cache poisoning.

### Polluted ONOS host table (SDN level)

In the ONOS window:

```
hosts
```

The attacker's MAC (`00:00:00:00:00:01`) now falsely owns all three IPs:
`[10.0.10.12, 10.0.10.11, 10.0.10.66]`. The controller's host database is poisoned.

### Interception (traffic through the attacker)

```
h1 ping -c 20 h2 > /dev/null &
atk timeout 8 tcpdump -i atk-eth0 -n icmp
```

tcpdump on the attacker prints the victims' ping packets passing through it.
The ping TTL also drops from 64 to 63 (one extra hop = the attacker).

---

## Stop the attack and clean up

```
atk pkill -f arp_attack
exit
sudo mn -c
```
