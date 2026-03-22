#!/usr/bin/env bash

set -euo pipefail

PI_HOST="${PI_HOST:-192.168.68.97}"
PI_USER="${PI_USER:-pi}"
PI_PATH="${PI_PATH:-/home/pi/Shadowbox}"
LOCAL_PATH="${LOCAL_PATH:-/Users/mdavidson/Shadowbox/}"
INSTALL_REQUIREMENTS="${INSTALL_REQUIREMENTS:-1}"

echo "Deploying Shadowbox to ${PI_USER}@${PI_HOST}:${PI_PATH}"

rsync -av --delete --progress \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  "${LOCAL_PATH}" \
  "${PI_USER}@${PI_HOST}:${PI_PATH}/"

if [[ "${INSTALL_REQUIREMENTS}" == "1" ]]; then
  ssh "${PI_USER}@${PI_HOST}" \
    "cd '${PI_PATH}' && '${PI_PATH}/.venv/bin/python' -m pip install -r '${PI_PATH}/requirements.txt'"
fi

ssh "${PI_USER}@${PI_HOST}" \
  "sudo systemctl restart shadowbox && sudo systemctl status shadowbox --no-pager -l"
