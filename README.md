Shadowbox Installation

This installs the Shadowbox hardware UI for RNBO Runner on a Raspberry Pi.

Tested on:

• Raspberry Pi OS Bookworm
• Raspberry Pi 4 / 5

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

On the RNBO image, do not run sudo apt upgrade. The RNBO image expects specific package versions.

Install only the packages Shadowbox requires.

Run:

sudo apt update

sudo apt install -y python3-venv python3-pip git pigpio python3-smbus i2c-tools

Enable the pigpio daemon:

sudo systemctl enable pigpiod
sudo systemctl start pigpiod

⸻

3. RNBO sanity check

Before installing Shadowbox, confirm RNBO Runner is working correctly.

Check installed RNBO packages:

dpkg -l | grep -i rnbo

You should see packages similar to:

rnbooscquery
rnbo-runner-panel
rnbo-update-service

Check OSCQuery directly:

curl http://127.0.0.1:5678

If RNBO Runner is healthy this should return a JSON tree describing the RNBO system.

Check service status:

systemctl status rnbooscquery.service –no-pager
systemctl status rnbo-runner-panel.service –no-pager

⸻

4. RNBO package compatibility note

A common failure occurs when rnbo-runner-panel requires a newer version of rnbooscquery.

Check available versions:

apt-cache policy rnbooscquery

If necessary upgrade the runner first:

sudo apt install rnbooscquery=1.4.3

Then install the panel:

sudo apt install rnbo-runner-panel

If the panel service is masked, unmask it:

sudo systemctl unmask rnbo-runner-panel.service
sudo systemctl enable rnbo-runner-panel.service
sudo systemctl start rnbo-runner-panel.service

The RNBO web interface should then be available at:

http://:3000

⸻

5. Clone the Shadowbox repository

cd ~
git clone https://github.com/stretta/shadowbox.git
cd shadowbox

⸻

6. Create Python virtual environment

Create the environment:

python3 -m venv .venv

Activate it:

source .venv/bin/activate

Install Python dependencies:

pip install -r requirements.txt

⸻

7. Test I2C display

Run the display test:

python -m tools.display_test

You should see a test pattern on the OLED display.

If nothing appears, confirm the I2C device address:

i2cdetect -y 1

Typical OLED address is:

0x3C

⸻

8. Test encoder

Run the encoder test:

python -m tools.encoder_test

Rotating the encoder should print movement values in the terminal.

⸻

9. Encoder + display test

Run the combined test:

python -m tools.encoder_display_test

Turning the encoder should update values on the OLED display.

⸻

10. Install the Shadowbox service

From the repository root run:

sudo ./install.sh

This installs a systemd service named:

shadowbox.service

⸻

11. Start the service

sudo systemctl start shadowbox

Check status:

systemctl status shadowbox

⸻

12. Enable auto-start

Enable Shadowbox to start on boot:

sudo systemctl enable shadowbox

Shadowbox will now launch automatically when the Raspberry Pi starts.

⸻

Repository layout

shadowbox/
├── install.sh
├── requirements.txt
├── README.md
├── service/
│   └── shadowbox.service
├── shadowbox/
│   ├── shadowbox.py
│   ├── ui.py
│   ├── renderer.py
│   ├── rnbo.py
│   ├── encoder.py
│   └── display.py
└── tools/
├── display_test.py
├── encoder_test.py
└── encoder_display_test.py

⸻

Troubleshooting

RNBO Runner not responding

Check OSCQuery:

curl http://127.0.0.1:5678

Restart services if necessary:

sudo systemctl restart rnbooscquery
sudo systemctl restart rnbo-runner-panel

⸻

Display not detected

Check I2C bus:

i2cdetect -y 1

Expected address is usually:

0x3C

⸻

Shadowbox service logs

To view runtime logs:

journalctl -u shadowbox -f