#!/usr/bin/env bash
#
# Attack 2 -- teardown. Removes the DNS-hijack flows installed by dns_hijack.sh,
# restoring normal resolution (the victim's query returns the legit answer again).
#
# Usage:  sudo bash dns_restore.sh
set -euo pipefail

ENV_FILE=/tmp/dns_hijack_env.sh
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Was the topology started?" >&2
    exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

OFCTL="ovs-ofctl -O OpenFlow13"

# Delete only our two flows (match them precisely; priority is not part of a
# delete match, so we match on the fields that identify them).
$OFCTL del-flows "${SW}" "udp,in_port=${P_H1},nw_dst=${LEGIT_DNS},tp_dst=53"
$OFCTL del-flows "${SW}" "udp,in_port=${P_H3},nw_src=${ROGUE_IP},tp_src=53"

echo "Removed hijack flows from ${SW}. Remaining DNS-matching flows (should be none):"
$OFCTL dump-flows "${SW}" | grep -E 'tp_dst=53|tp_src=53' || echo "  (none)"
echo
echo "Verify from the Mininet CLI:  h1 dig +short @${LEGIT_DNS} www.lab.example"
echo "  expect ${LEGIT_ANSWER} again."
