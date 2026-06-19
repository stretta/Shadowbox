#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: wifi_network.sh <list|rescan|status|connect|connect-new> [connection-id|ssid] [password]
EOF
}

require_nmcli() {
  if ! command -v nmcli >/dev/null 2>&1; then
    echo "nmcli unavailable" >&2
    exit 1
  fi
}

connect_saved_network() {
  local connection_id="$1"
  if [[ -z "${connection_id}" ]]; then
    echo "connection id required" >&2
    exit 1
  fi

  if ! nmcli -t -f NAME,TYPE connection show | grep -Fqx "${connection_id}:802-11-wireless"; then
    echo "network not saved" >&2
    exit 1
  fi

  nmcli connection up id "${connection_id}"
}

connect_new_network() {
  local ssid="$1"
  local password="${2:-}"
  if [[ -z "${ssid}" ]]; then
    echo "ssid required" >&2
    exit 1
  fi

  if [[ -n "${password}" ]]; then
    nmcli device wifi connect "${ssid}" password "${password}"
  else
    nmcli device wifi connect "${ssid}"
  fi
}

cmd="${1:-}"
case "${cmd}" in
  list)
    require_nmcli
    nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list --rescan no
    ;;
  rescan)
    require_nmcli
    nmcli device wifi rescan
    sleep "${SHADOWBOX_WIFI_RESCAN_SETTLE_SECONDS:-3}"
    nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list --rescan no
    ;;
  status)
    require_nmcli
    nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status
    ;;
  connect)
    require_nmcli
    connect_saved_network "${2:-}"
    ;;
  connect-new)
    require_nmcli
    connect_new_network "${2:-}" "${3:-}"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
