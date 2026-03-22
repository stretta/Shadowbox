# Shadowbox

Shadowbox is a hardware UI for RNBO Runner designed for Raspberry Pi systems running RNBO exports.

It provides:

- Instance browsing
- Instance lifecycle control
- Parameter editing
- Preset loading
- Audio and MIDI routing
- Basic system management
- Display interface for SSD1306, SSD1309, and ST7789 hardware
- Rotary encoder navigation

Shadowbox complements the RNBO Runner web interface by providing a minimal physical control surface.

---

# Documentation

- [docs/uispec.md](./docs/uispec.md): UI behavior and interaction rules
- [docs/architecture.md](./docs/architecture.md): codebase and runtime structure
- [docs/walkthrough.md](./docs/walkthrough.md): end-to-end RNBO-to-Shadowbox editor flow, including `step16`

---

# Hardware

Typical configuration:

- Raspberry Pi 4 / 5
- 128×32 I2C OLED display (SSD1306)
- Rotary encoder with push button

Also supported:

- 128x64 I2C OLED display (SSD1309)
- 240x320 SPI TFT display (ST7789)
- Waveshare 2-inch LCD Module (ST7789V, 240x320 SPI)

Example OLED module:

https://www.adafruit.com/product/4484

---

# Features

- Instance browsing from RNBO Runner
- Add instance from published patcher list
- Replace or remove an existing instance when the backend publishes those commands
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

# 1. Enable I2C / SPI

Run:

```
sudo raspi-config
```

Navigate to:

Interface Options → I2C → Enable
Interface Options → SPI → Enable

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
i2c-tools \
python3-spidev \
python3-rpi.gpio
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

# 6. Create Python virtual environment

Create environment:

```
python3 -m venv .venv
```

Activate it:

```
source .venv/bin/activate
```

Install Python dependencies:

```
pip install -r requirements.txt
```

---

# 7. Test I2C display

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

# 8. Test encoder

Run:

```
python -m tools.encoder_test
```

Rotating the encoder should print movement values.

---

# 9. Encoder + display test

Run:

```
python -m tools.encoder_display_test
```

Turning the encoder should update the OLED display.

---

# 10. Install the Shadowbox service

From the repository root:

```
./install.sh
```

This installs the service:

```
shadowbox.service
```

The installer uses `sudo` only for system package and service steps. It creates the virtual environment as your current user and generates a systemd unit for the current repository path.

Display selection is controlled through environment variables. The service reads an optional config file at:

```
/etc/default/shadowbox
```

Example ST7789 configuration:

```
SHADOWBOX_DISPLAY=st7789
SHADOWBOX_ST7789_SPI_BUS=0
SHADOWBOX_ST7789_SPI_CS=0
SHADOWBOX_ST7789_DC=9
SHADOWBOX_ST7789_RST=13
SHADOWBOX_ST7789_BACKLIGHT=19
SHADOWBOX_ST7789_ROTATION=90
SHADOWBOX_ST7789_WIDTH=320
SHADOWBOX_ST7789_HEIGHT=240
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
```

Example Waveshare 2-inch configuration:

``` 
SHADOWBOX_DISPLAY=waveshare_2inch
SHADOWBOX_WAVESHARE_SPI_BUS=0
SHADOWBOX_WAVESHARE_SPI_CS=0
SHADOWBOX_WAVESHARE_DC=25
SHADOWBOX_WAVESHARE_RST=27
SHADOWBOX_WAVESHARE_BACKLIGHT=18
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
```

The TFT backends now default to a full `320x240` logical framebuffer. You can
still override `SHADOWBOX_LOGICAL_WIDTH` and `SHADOWBOX_LOGICAL_HEIGHT` if you
want the older scaled-up rendering behavior while tuning layouts.

If the display uses `GPIO27` for reset, remap the encoder off that pin:

```
SHADOWBOX_ENCODER_CLK=17
SHADOWBOX_ENCODER_DT=26
SHADOWBOX_ENCODER_SW=22
```

Encoder feel can also be tuned from the service env file:

```
SHADOWBOX_ENCODER_STEPS_PER_DETENT=4
SHADOWBOX_ENCODER_AB_GLITCH_US=200
SHADOWBOX_ENCODER_SW_GLITCH_US=8000
SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS=0.035
SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER=2
SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS=0.018
SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER=3
```

Lower `STEPS_PER_DETENT` makes one click register sooner. Higher `AB_GLITCH_US`
filters more bounce but can make the knob feel heavier. The acceleration values
let slow turns stay precise while fast turns jump farther through long lists.

OLED examples:

```
SHADOWBOX_DISPLAY=ssd1306
SHADOWBOX_I2C_BUS=1
SHADOWBOX_I2C_ADDR=0x3C
```

```
SHADOWBOX_DISPLAY=ssd1309
SHADOWBOX_I2C_BUS=1
SHADOWBOX_I2C_ADDR=0x3C
```

---

# 11. Start the service

```
sudo systemctl start shadowbox
```

Check status:

```
systemctl status shadowbox
```

---

# 12. Enable auto-start

```
sudo systemctl enable shadowbox
```

Shadowbox will now start automatically on boot.

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
│   ├── shadowbox.py
│   ├── ui.py
│   ├── renderer.py
│   ├── rnbo.py
│   ├── encoder.py
│   └── display/
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
