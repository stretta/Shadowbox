#!/bin/bash

echo "Installing Shadowbox..."

sudo apt update
sudo apt install -y python3-venv pigpio python3-smbus

cd ~

git clone https://github.com/YOURNAME/shadowbox.git
cd shadowbox

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "Installation complete"