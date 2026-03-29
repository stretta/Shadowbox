#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tools/deploy_pi.sh [options]

Options:
  --host <host>         Override the resolved Pi hostname or address.
  --alias <name>        Use a named host alias (pt4, studio, bench).
  --path <path>         Override the remote deploy path.
  --user <user>         Override the SSH user.
  --local-path <path>   Override the local repo path to sync.
  --dry-run             Show what would happen without modifying the remote host.
  --sync-only           Sync files only. Skip requirements install and restart.
  --restart             Force a restart after sync.
  --install-deps        Install requirements after sync.
  --no-install-deps     Skip requirements install.
  --help                Show this help text.

Environment overrides still work: PI_HOST, PI_USER, PI_PATH, LOCAL_PATH,
INSTALL_REQUIREMENTS, and RESTART_SERVICE.
EOF
}

require_value() {
  if [[ $# -lt 2 || -z "${2:-}" ]]; then
    echo "Missing value for option '$1'." >&2
    usage >&2
    exit 1
  fi
}

resolve_host_alias() {
  local alias_name="$1"
  local alias_upper
  alias_upper="$(printf '%s' "${alias_name}" | tr '[:lower:]' '[:upper:]')"
  local override_var="PI_HOST_ALIAS_${alias_upper}"
  local override_value="${!override_var:-}"

  if [[ -n "${override_value}" ]]; then
    printf '%s\n' "${override_value}"
    return
  fi

  case "${alias_name}" in
    pt4)
      printf '%s\n' "pt4.local"
      ;;
    studio)
      printf '%s\n' "192.168.68.97"
      ;;
    bench)
      printf '%s\n' "shadowbox-bench.local"
      ;;
    *)
      echo "Unknown host alias '$1'. Known aliases: pt4, studio, bench." >&2
      exit 1
      ;;
  esac
}

resolve_host_address() {
  local host="$1"
  local resolved=""

  if [[ "${host}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    printf '%s\n' "${host}"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    resolved="$(
      python3 -c 'import socket, sys
host = sys.argv[1]
try:
    print(socket.gethostbyname(host))
except OSError:
    pass' "${host}"
    )"
  fi

  if [[ -n "${resolved}" ]]; then
    printf '%s\n' "${resolved}"
    return
  fi

  printf '%s\n' "${host}"
}

PI_HOST="${PI_HOST:-192.168.68.97}"
PI_USER="${PI_USER:-pi}"
PI_PATH="${PI_PATH:-/home/pi/Shadowbox}"
LOCAL_PATH="${LOCAL_PATH:-/Users/mdavidson/Documents/Repos/Shadowbox/}"
INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-1}"
RESTART_SERVICE="${RESTART_SERVICE:-1}"
DRY_RUN=0
HOST_ALIAS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      require_value "$@"
      PI_HOST="$2"
      shift 2
      ;;
    --alias)
      require_value "$@"
      HOST_ALIAS="$2"
      shift 2
      ;;
    --path)
      require_value "$@"
      PI_PATH="$2"
      shift 2
      ;;
    --user)
      require_value "$@"
      PI_USER="$2"
      shift 2
      ;;
    --local-path)
      require_value "$@"
      LOCAL_PATH="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --sync-only)
      INSTALL_REQUIREMENTS=0
      RESTART_SERVICE=0
      shift
      ;;
    --restart)
      RESTART_SERVICE=1
      shift
      ;;
    --install-deps)
      INSTALL_REQUIREMENTS=1
      shift
      ;;
    --no-install-deps)
      INSTALL_REQUIREMENTS=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -n "${HOST_ALIAS}" ]]; then
  PI_HOST="$(resolve_host_alias "${HOST_ALIAS}")"
fi

RESOLVED_PI_HOST="$(resolve_host_address "${PI_HOST}")"

if [[ "${PI_PATH}" == "/home/pi/shadowbox" ]]; then
  echo "Refusing to deploy to legacy path '${PI_PATH}'. Use /home/pi/Shadowbox."
  exit 1
fi

if [[ "${LOCAL_PATH}" != */ ]]; then
  LOCAL_PATH="${LOCAL_PATH}/"
fi

if [[ ! -d "${LOCAL_PATH}" ]]; then
  echo "Local path '${LOCAL_PATH}' does not exist." >&2
  exit 1
fi

echo "Deploying Shadowbox to ${PI_USER}@${RESOLVED_PI_HOST}:${PI_PATH}"
if [[ -n "${HOST_ALIAS}" ]]; then
  echo "Resolved host alias '${HOST_ALIAS}' to '${PI_HOST}'"
fi
if [[ "${RESOLVED_PI_HOST}" != "${PI_HOST}" ]]; then
  echo "Resolved '${PI_HOST}' to IP '${RESOLVED_PI_HOST}'"
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "Dry run enabled: remote state will not be modified."
  echo "Dry run still connects to the target host so rsync can compare file trees."
fi

if [[ "${RESOLVED_PI_HOST}" == "${PI_HOST}" && "${PI_HOST}" != "localhost" && ! "${PI_HOST}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  if [[ -n "${HOST_ALIAS}" ]]; then
    HOST_ALIAS_UPPER="$(printf '%s' "${HOST_ALIAS}" | tr '[:lower:]' '[:upper:]')"
    echo "Could not resolve '${PI_HOST}' to an IP address." >&2
    echo "If mDNS is unavailable on this Mac, re-run with --host <ip> or set PI_HOST_ALIAS_${HOST_ALIAS_UPPER}=<ip>." >&2
    exit 1
  fi
fi

RSYNC_OPTS=(-av --delete --progress)
if [[ "${DRY_RUN}" == "1" ]]; then
  RSYNC_OPTS+=(--dry-run)
fi

if [[ "${DRY_RUN}" != "1" ]]; then
  ssh "${PI_USER}@${RESOLVED_PI_HOST}" "mkdir -p '${PI_PATH}'"
else
  echo "Would create remote directory '${PI_PATH}'"
fi

rsync "${RSYNC_OPTS[@]}" \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${LOCAL_PATH}" \
  "${PI_USER}@${RESOLVED_PI_HOST}:${PI_PATH}/"

if [[ "${INSTALL_REQUIREMENTS}" == "1" ]]; then
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "Would install Python requirements in '${PI_PATH}/.venv'"
  else
    ssh "${PI_USER}@${RESOLVED_PI_HOST}" \
      "cd '${PI_PATH}' && '${PI_PATH}/.venv/bin/python' -m pip install -r '${PI_PATH}/requirements.txt'"
  fi
fi

if [[ "${RESTART_SERVICE}" == "1" ]]; then
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "Would restart the 'shadowbox' service and show its status"
  else
    ssh "${PI_USER}@${RESOLVED_PI_HOST}" \
      "sudo systemctl restart shadowbox && sudo systemctl status shadowbox --no-pager -l"
  fi
else
  echo "Skipping service restart."
fi
