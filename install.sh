#!/usr/bin/env bash

set -e

cd "$(dirname "$0")"

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

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing systemd service..."
sudo cp service/shadowbox.service /etc/systemd/system/shadowbox.service

echo "Reloading systemd..."
sudo systemctl daemon-reload

echo "Enabling Shadowbox service..."
sudo systemctl enable shadowbox

echo "Starting Shadowbox..."
sudo systemctl restart shadowbox

echo ""
echo "Install complete."
echo ""
echo "Check status with:"
echo "systemctl status shadowbox"
echo ""
echo "Check logs with:"
echo "journalctl -u shadowbox -n 100 --no-pager"
echo ""
echo "Reboot recommended:"
echo "sudo reboot"