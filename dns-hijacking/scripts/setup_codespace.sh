#!/usr/bin/env bash
# One-time environment setup for running the DNS-hijack testbed inside a
# GitHub Codespace (Ubuntu container). Run with sudo:  sudo bash setup_codespace.sh
#
# Installs Mininet, Open vSwitch, dnsmasq, capture + traffic tools, and
# starts ONOS in Docker. Safe to re-run.
set -e

echo "[*] Installing packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y mininet openvswitch-switch openvswitch-common \
    dnsmasq dnsutils tcpdump iperf3 python3 curl

echo "[*] Starting Open vSwitch..."
service openvswitch-switch start || /usr/share/openvswitch/scripts/ovs-ctl start || true

# dnsmasq must NOT run as a system service here (we launch it per-host in
# Mininet), so stop/disable the global one to free port 53.
systemctl disable --now dnsmasq 2>/dev/null || service dnsmasq stop 2>/dev/null || true

echo "[*] Starting ONOS in Docker (this pulls ~1GB the first time)..."
if ! command -v docker >/dev/null 2>&1; then
    echo "[!] docker not found. In a Codespace it is usually preinstalled."
    echo "    Install Docker, then re-run this script."
    exit 1
fi

# Remove any previous container, then launch ONOS 2.7 LTS.
docker rm -f onos 2>/dev/null || true
docker run -d --name onos \
    -p 8181:8181 -p 8101:8101 -p 6653:6653 -p 6640:6640 \
    onosproject/onos:2.7.0

echo
echo "[*] ONOS is starting. Give it ~60-90 seconds, then activate the apps:"
echo
echo "    # OpenFlow provider + reactive forwarding (needed for baseline + host learning)"
echo "    curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.openflow/active"
echo "    curl -u onos:rocks -X POST http://localhost:8181/onos/v1/applications/org.onosproject.fwd/active"
echo
echo "[*] Check ONOS is ready (should return JSON):"
echo "    curl -u onos:rocks http://localhost:8181/onos/v1/devices"
echo
echo "[*] Setup done."
