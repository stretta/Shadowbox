Shadowbox Installation

This installs the Shadowbox hardware UI for RNBO Runner on a Raspberry Pi.

Tested on:

Raspberry Pi OS Bookworm
Raspberry Pi 4 / 5

⸻

1. Enable I2C

Run:

sudo raspi-config

Navigate to:

Interface Options → I2C → Enable

Then reboot:

sudo reboot

⸻

2. Install system dependencies

Run:

sudo apt update

sudo apt install -y 
python3-venv 
python3-pip 
git 
pigpio 
python3-smbus 
i2c-tools

Enable the pigpio daemon:

sudo systemctl enable pigpiod
sudo systemctl start pigpiod

⸻

3. Clone the repository

cd ~
git clone https://github.com/stretta/Shadowbox.git
cd Shadowbox

⸻

4. Create the Python environment

python3 -m venv .venv

Activate it:

source .venv/bin/activate

Upgrade pip:

pip install –upgrade pip

Install Python dependencies:

pip install -r requirements.txt

⸻

5. Test the OLED

Before running Shadowbox, verify the display works.

Stop the Shadowbox service if running:

sudo systemctl stop shadowbox

Run the display test:

python -m tools.display_test

You should see:

SHADOWBOX
display OK

on the OLED.

⸻

6. Test the encoder + display

Run:

python -m tools.encoder_display_test

This displays encoder movement and button state on the OLED.

Rotate the encoder and press the button to confirm operation.

⸻

7. Install the system service

Install the service file:

sudo cp service/shadowbox.service /etc/systemd/system/

Reload systemd:

sudo systemctl daemon-reload

Enable the service:

sudo systemctl enable shadowbox

Start it:

sudo systemctl start shadowbox

⸻

8. Verify operation

Check service status:

systemctl status shadowbox

Expected output includes:

active (running)

Example:

Active: active (running)

⸻

9. Test automatic startup

Reboot the Pi:

sudo reboot

Shadowbox should start automatically and load the last patch.

⸻

Development / debugging

To run Shadowbox manually:

sudo systemctl stop shadowbox

cd ~/Shadowbox
source .venv/bin/activate
python -m shadowbox.shadowbox

Restart the service when finished:

sudo systemctl start shadowbox

⸻

Hardware diagnostics

Display test

python -m tools.display_test

Encoder test

python -m tools.encoder_display_test

⸻

Common issues

Display appears corrupted

This usually means two processes are writing to the OLED.

Stop the service before running tests:

sudo systemctl stop shadowbox

⸻

pigpio connection error

Start the pigpio daemon:

sudo systemctl start pigpiod

⸻

OLED not detected

Verify I2C:

i2cdetect -y 1

The display should appear at address:

3c

⸻

Repository layout

Shadowbox/

shadowbox/
 shadowbox.py
 display.py
 renderer.py
 encoder.py
 rnbo.py
 ui.py

tools/
 display_test.py
 encoder_display_test.py

service/
 shadowbox.service

install.sh
requirements.txt
README.md