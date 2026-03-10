#!/usr/bin/env bash

set -e

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
sudo cp service/shadowbox.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable shadowbox

echo "Starting Shadowbox..."
sudo systemctl start shadowbox

echo ""
echo "Install complete."
echo ""
echo "Reboot recommended:"
echo "sudo reboot"