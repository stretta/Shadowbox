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
DISPLAY_KIND="${SHADOWBOX_DISPLAY:-ssd1309}"

echo "Shadowbox installer"
echo "==================="
echo "Display backend: ${DISPLAY_KIND}"

echo "Updating system..."
sudo apt update

echo "Installing system dependencies..."
sudo apt install -y \
    python3-venv \
    python3-pip \
    pigpio \
    python3-spidev \
    python3-rpi.gpio

case "${DISPLAY_KIND}" in
    ssd1306|ssd1309)
        echo "Installing OLED/I2C dependencies..."
        sudo apt install -y \
            python3-smbus \
            i2c-tools

        echo "Enabling I2C..."
        sudo raspi-config nonint do_i2c 0
        ;;
    st7789|st7789_raw|waveshare_2inch)
        echo "Skipping I2C setup for TFT display backend."
        ;;
    *)
        echo "Unknown SHADOWBOX_DISPLAY='${DISPLAY_KIND}'."
        echo "Skipping display-specific I2C setup."
        ;;
esac

echo "Enabling SPI..."
sudo raspi-config nonint do_spi 0

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
Wants=pigpiod.service
After=network.target pigpiod.service

[Service]
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_PYTHON} -m shadowbox.shadowbox
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/default/shadowbox

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable shadowbox

echo "Starting Shadowbox..."
sudo systemctl restart shadowbox

echo ""
echo "Install complete."
echo ""
echo "Reboot recommended:"
echo "sudo reboot"
