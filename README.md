# Shadowbox

Shadowbox is a hardware UI for RNBO Runner designed for Raspberry Pi systems running RNBO exports.

It provides:

- Patch selection
- Parameter editing
- Basic system management
- OLED display interface
- Rotary encoder navigation

Shadowbox complements the RNBO Runner web interface by providing a minimal physical control surface.

---

# Hardware

Typical configuration:

- Raspberry Pi 4 / 5
- A display:
    - 128×32 I2C OLED display (SSD1306) or
    - 128×64 I2C OLED display (SSD1309)
- Rotary encoder with push button

Example OLED module:

https://www.adafruit.com/product/4484

---

# Features

- Patch selection from RNBO Runner
- Parameter editing
- Graphical value feedback
- OLED dim/sleep management
- Encoder navigation
- RNBO OSCQuery integration
- System status display
- Audio device switching
- JACK restart
- Startup configuration

---

# Installation

These instructions assume a fresh RNBO Raspberry Pi image.

Tested on:

- Raspberry Pi OS Bookworm
- Raspberry Pi 4 / 5

---

# 1. Enable I2C

Run:

```
sudo raspi-config
```

Navigate to:

Interface Options → I2C → Enable

Then reboot:

```
sudo reboot
```

---

# 2. Install dependencies

⚠️ On the RNBO image **do not run `sudo apt upgrade`**.

Install only the required packages:

```
sudo apt update

sudo apt install -y \
python3-venv \
python3-pip \
git \
pigpio \
python3-smbus \
i2c-tools
```

Enable pigpio:

```
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

---

# 3. Verify RNBO Runner

Check installed RNBO packages:

```
dpkg -l | grep -i rnbo
```

Expected packages:

- rnbooscquery
- rnbo-runner-panel
- rnbo-update-service

Verify OSCQuery:

```
curl http://127.0.0.1:5678
```

This should return a JSON tree describing the RNBO system.

Check service status:

```
systemctl status rnbooscquery.service
systemctl status rnbo-runner-panel.service
```

---

# 4. RNBO package compatibility

A common failure occurs when `rnbo-runner-panel` requires a newer version of `rnbooscquery`.

Check available versions:

```
apt-cache policy rnbooscquery
```

If necessary upgrade the runner first:

```
sudo apt install rnbooscquery=1.4.3
```

Then install the panel:

```
sudo apt install rnbo-runner-panel
```

If the panel service is masked:

```
sudo systemctl unmask rnbo-runner-panel.service
sudo systemctl enable rnbo-runner-panel.service
sudo systemctl start rnbo-runner-panel.service
```

The web interface should appear at:

http://<pi-ip>:3000

---

# 5. Clone the repository

```
cd ~

git clone https://github.com/stretta/shadowbox.git

cd shadowbox
```

---

# 6. Install Shadowbox

From the repository root:
```
cd ~/shadowbox
chmod +x install.sh
./install.sh
```
Do not run the installer with `sudo`.
The script uses `sudo` internally only where required.

---

# 7. Verify installation


```
systemctl status shadowbox
```

```
journalctl -u shadowbox -n 100 --no-pager
```
---

# 8. Test I2C display

Activate the virtual environment:

```
source .venv/bin/activate

```
Run:

```
python -m tools.display_test
```

You should see a test pattern on the OLED.

If nothing appears check the I2C device address:

```
i2cdetect -y 1
```

Typical OLED address:

```
0x3C
```

---

# 9. Test encoder

Run:

```
python -m tools.encoder_test
```

Rotating the encoder should print movement values.

---

# 10. Encoder + display test

Run:

```
python -m tools.encoder_display_test
```

Turning the encoder should update the OLED display.

---

# Repository layout

```
shadowbox/
├── install.sh
├── requirements.txt
├── README.md
├── service/
│   └── shadowbox.service
├── shadowbox/
│   ├── __init__.py
│   ├── shadowbox.py
│   ├── ui.py
│   ├── renderer.py
│   ├── rnbo.py
│   ├── encoder.py
│   ├── core.py
│   ├── ttid.py
│   └── display.py
└── tools/
    ├── display_test.py
    ├── encoder_test.py
    └── encoder_display_test.py
```

---

# Troubleshooting

## RNBO Runner not responding

Check OSCQuery:

```
curl http://127.0.0.1:5678
```

Restart services:

```
sudo systemctl restart rnbooscquery
sudo systemctl restart rnbo-runner-panel
```

---

## Display not detected

Check I2C bus:

```
i2cdetect -y 1
```

Expected address:

```
0x3C
```

---

## Shadowbox logs

View runtime logs:

```
journalctl -u shadowbox -f
```
