#!/usr/bin/env bash

set -euo pipefail

INTERFACE="${SHADOWBOX_DIRECT_ETHERNET_IFACE:-eth0}"
CIDR="${SHADOWBOX_DIRECT_ETHERNET_CIDR:-10.42.0.1/24}"

usage() {
  cat <<'EOF'
Usage: direct_ethernet.sh <enable|disable|status>
EOF
}

require_interface() {
  if [[ ! -d "/sys/class/net/${INTERFACE}" ]]; then
    echo "interface '${INTERFACE}' not found" >&2
    exit 1
  fi
}

has_cidr() {
  ip -4 -o addr show dev "${INTERFACE}" | awk '{print $4}' | grep -Fxq "${CIDR}"
}

cmd="${1:-}"
if [[ -z "${cmd}" ]]; then
  usage >&2
  exit 1
fi

require_interface

case "${cmd}" in
  enable)
    ip link set dev "${INTERFACE}" up
    ip addr replace "${CIDR}" dev "${INTERFACE}"
    ;;
  disable)
    if has_cidr; then
      ip addr del "${CIDR}" dev "${INTERFACE}"
    fi
    ;;
  status)
    if has_cidr; then
      echo "ACTIVE"
    else
      echo "OFF"
    fi
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
