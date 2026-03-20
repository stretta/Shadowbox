#!/usr/bin/env bash

set -e

if [[ "${EUID}" -eq 0 ]]; then
    echo "Do not run install.sh with sudo."
    echo "Run it as your normal user from the repository root:"
    echo "./install.sh"
    exit 1
fi

REPO_DIR="$(pwd)"
RUN_USER="$(id -un)"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
SERVICE_PATH="/etc/systemd/system/shadowbox.service"

echo "Shadowbox installer"
echo "==================="

echo "Updating system..."
sudo apt update

echo "Installing system dependencies..."
sudo apt install -y \
    python3-venv \
    python3-pip \
    python3-smbus \
    i2c-tools \
    pigpio

echo "Enabling I2C..."
sudo raspi-config nonint do_i2c 0

echo "Starting pigpio daemon..."
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "Creating Python virtual environment..."
python3 -m venv .venv

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing systemd service..."
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=Shadowbox RNBO Hardware UI
After=network.target

[Service]
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m shadowbox.shadowbox
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable shadowbox

echo "Starting Shadowbox..."
sudo systemctl start shadowbox

echo ""
echo "Install complete."
echo ""
echo "Reboot recommended:"
echo "sudo reboot"
