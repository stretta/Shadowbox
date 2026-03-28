# Shadowbox

Shadowbox is a hardware UI for RNBO Runner designed for Raspberry Pi systems running RNBO exports.

It provides:

- Instance browsing
- Instance lifecycle control
- Parameter editing
- Preset loading
- Audio and MIDI routing
- Basic system management
- Startup audio-device recall
- Startup discovery/status screen
- Display interface for SSD1306, SSD1309, and ST7789 hardware
- Rotary encoder navigation
- Custom parameter editors for `step16`, TTID, and pitch display metadata

Shadowbox complements the RNBO Runner web interface by providing a minimal physical control surface.

---

# Documentation

- [docs/uispec.md](./docs/uispec.md): UI behavior and interaction rules
- [docs/architecture.md](./docs/architecture.md): codebase and runtime structure
- [docs/walkthrough.md](./docs/walkthrough.md): end-to-end RNBO-to-Shadowbox editor flow, including `step16`
- [docs/wiring.md](./docs/wiring.md): encoder and display wiring reference

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
- Saved UI state in `~/rnbo-ui/shadowbox_state.json`

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

For OLED builds:

```
Interface Options → I2C → Enable
```

For SPI TFT builds:

```
Interface Options → SPI → Enable
```

If you are using a TFT-only build, I2C is not required.

Then reboot:

```
sudo reboot
```

---

# 2. Install dependencies

⚠️ On the RNBO image **do not run `sudo apt upgrade`**.

Install the required packages:

```
sudo apt update

sudo apt install -y \
python3-venv \
python3-pip \
git \
pigpio \
python3-spidev \
python3-rpi.gpio
```

For OLED builds, also install:

```
sudo apt install -y python3-smbus i2c-tools
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

git clone https://github.com/stretta/shadowbox.git Shadowbox

cd Shadowbox
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

Run Shadowbox directly:

```
python -m shadowbox.shadowbox
```

On TFT builds, export the display backend first or Shadowbox will fall back to
the default OLED backend (`ssd1309`), which expects `/dev/i2c-1`.

Library-backed ST7789 example:

```
export SHADOWBOX_DISPLAY=st7789
python -m shadowbox.shadowbox
```

Raw ST7789 example for custom modules that stay blank with the library-backed
driver:

```
export SHADOWBOX_DISPLAY=st7789_raw
python -m shadowbox.shadowbox
```

Use `waveshare_2inch` instead if that matches your display wiring.

If `pigpiod` is not running, startup will fail with `RuntimeError: pigpio daemon not running`.

---

# 7. Test display

For OLED builds:

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

For ST7789 TFT builds, use the raw hardware test:

```
python -m tools.st7789_raw_test
```

If the raw test works but `SHADOWBOX_DISPLAY=st7789` stays blank, use
`SHADOWBOX_DISPLAY=st7789_raw`.

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

The installer checks `SHADOWBOX_DISPLAY` to decide whether I2C setup is needed.
For TFT builds, export the display backend before running it so the installer can
skip OLED/I2C setup:

```
export SHADOWBOX_DISPLAY=st7789_raw
./install.sh
```

This installs the service:

```
shadowbox.service
```

The installer uses `sudo` only for system package and service steps. It creates the virtual environment as your current user and generates a systemd unit for the current repository path.

The repository also includes a static unit file at:

```
service/shadowbox.service
```

That file is a template for `/home/pi/Shadowbox`. If your checkout lives elsewhere, either use `./install.sh` or update the unit before installing it manually.

Display selection is controlled through environment variables. The service reads an optional config file at:

```
/etc/default/shadowbox
```

You can also choose where Shadowbox lands after loading or replacing an instance:

```
SHADOWBOX_POST_LOAD_VIEW=instance
```

Supported values:

- `instance` keeps the current behavior and returns to the instance menu
- `parameters` jumps straight into the parameter list for the loaded instance
- `presets` jumps straight into the preset list for the loaded instance

For dim/sleep testing, you can override the idle behavior in `/etc/default/shadowbox`:

```
SHADOWBOX_DIM_TIMEOUT=3
SHADOWBOX_SLEEP_TIMEOUT=6
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

That makes the display dim after 3 seconds of no encoder activity and sleep after 6 seconds. On TFT backends, use `255/64`-style brightness values rather than OLED-style `127/16`, or the display can look dim immediately at startup.

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
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

The generic `st7789` backend uses the Python `st7789` package. Some custom
modules work better with the raw backend below.

If a custom ST7789 module works with `tools/st7789_raw_test.py` but stays blank
with the library-backed `st7789` driver, try the raw backend instead:

```
SHADOWBOX_DISPLAY=st7789_raw
SHADOWBOX_ST7789_SPI_BUS=0
SHADOWBOX_ST7789_SPI_CS=0
SHADOWBOX_ST7789_DC=25
SHADOWBOX_ST7789_RST=24
SHADOWBOX_ST7789_BACKLIGHT=18
SHADOWBOX_ST7789_ROTATION=0
SHADOWBOX_ST7789_WIDTH=320
SHADOWBOX_ST7789_HEIGHT=240
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
SHADOWBOX_ST7789_INVERT=1
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Known-good PT4 config:

`pt4.local`, raw ST7789 backend, `/home/pi/Shadowbox`

```sh
SHADOWBOX_DISPLAY=st7789_raw
SHADOWBOX_ST7789_SPI_BUS=0
SHADOWBOX_ST7789_SPI_CS=0
SHADOWBOX_ST7789_DC=25
SHADOWBOX_ST7789_RST=24
SHADOWBOX_ST7789_BACKLIGHT=18
SHADOWBOX_ST7789_ROTATION=0
SHADOWBOX_ST7789_WIDTH=320
SHADOWBOX_ST7789_HEIGHT=240
SHADOWBOX_ST7789_OFFSET_LEFT=0
SHADOWBOX_ST7789_OFFSET_TOP=0
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
SHADOWBOX_ST7789_INVERT=1
SHADOWBOX_ENCODER_CLK=17
SHADOWBOX_ENCODER_DT=27
SHADOWBOX_ENCODER_SW=22
SHADOWBOX_BACK_BUTTON_PIN=23
SHADOWBOX_BACK_BUTTON_GLITCH_US=8000
SHADOWBOX_DIM_TIMEOUT=120
SHADOWBOX_SLEEP_TIMEOUT=600
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Deploy to PT4:

```bash
ssh pi@pt4.local "mkdir -p /home/pi/Shadowbox" && \
rsync -av --delete --progress \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  /Users/mdavidson/Documents/Repos/Shadowbox/ \
  pi@pt4.local:/home/pi/Shadowbox/
```

Restart Shadowbox on PT4:

```bash
sudo systemctl restart shadowbox
sudo systemctl status shadowbox --no-pager -l
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
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

The TFT backends default to a full `320x240` logical framebuffer. You can still override `SHADOWBOX_LOGICAL_WIDTH` and `SHADOWBOX_LOGICAL_HEIGHT` if you want the older scaled-up rendering behavior while tuning layouts.

If the display uses `GPIO27` for reset, remap the encoder off that pin:

```
SHADOWBOX_ENCODER_CLK=17
SHADOWBOX_ENCODER_DT=26
SHADOWBOX_ENCODER_SW=22
SHADOWBOX_BACK_BUTTON_PIN=5
```

Encoder feel can also be tuned from the service env file:

```
SHADOWBOX_ENCODER_STEPS_PER_DETENT=4
SHADOWBOX_ENCODER_LONG_PRESS_SECONDS=0.6
SHADOWBOX_ENCODER_AB_GLITCH_US=200
SHADOWBOX_ENCODER_SW_GLITCH_US=8000
SHADOWBOX_BACK_BUTTON_GLITCH_US=8000
SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS=0.035
SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER=2
SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS=0.018
SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER=3
```

Lower `STEPS_PER_DETENT` makes one click register sooner. Higher `AB_GLITCH_US`
filters more bounce but can make the knob feel heavier. The acceleration values
let slow turns stay precise while fast turns jump farther through long lists.
If `SHADOWBOX_BACK_BUTTON_PIN` is set, that button emits the same normalized
`long_press` back/cancel gesture used throughout the UI.

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

If `SHADOWBOX_DISPLAY` is not set, Shadowbox currently defaults to `ssd1309`.

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

For direct deploys to a Pi on your network, there is also a helper script:

```
tools/deploy_pi.sh
```

It syncs the repo with `rsync`, optionally installs Python requirements in the remote `.venv`, and restarts the `shadowbox` service. Override `PI_HOST`, `PI_USER`, `PI_PATH`, and related environment variables as needed.

Helpful flags:

```bash
tools/deploy_pi.sh --alias pt4
tools/deploy_pi.sh --dry-run
tools/deploy_pi.sh --sync-only
tools/deploy_pi.sh --alias studio --no-install-deps
```

Built-in aliases currently include `pt4`, `studio`, and `bench`. Run `tools/deploy_pi.sh --help` to see all options.
`--dry-run` still connects to the Pi so `rsync` can compare the remote tree, but it does not change files or restart services.

---

# Repository layout

```
shadowbox/
├── assets/
├── docs/
│   ├── architecture.md
│   ├── uispec.md
│   ├── walkthrough.md
│   └── wiring.md
├── install.sh
├── requirements.txt
├── README.md
├── service/
│   └── shadowbox.service
├── shadowbox/
│   ├── data/
│   ├── editors/
│   ├── shadowbox.py
│   ├── ui.py
│   ├── renderer.py
│   ├── rnbo.py
│   ├── encoder.py
│   └── display/
└── tools/
    ├── deploy_pi.sh
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

For encoder and display pin mappings, see [docs/wiring.md](./docs/wiring.md).

---

## Encoder not responding

Check the pigpio daemon:

```
systemctl status pigpiod
```

If needed:

```
sudo systemctl restart pigpiod
```

If you have copied an updated `service/shadowbox.service` onto the Pi, reload the
installed unit before testing boot behavior:

```sh
sudo cp /home/pi/Shadowbox/service/shadowbox.service /etc/systemd/system/shadowbox.service
sudo systemctl daemon-reload
sudo systemctl enable pigpiod shadowbox
sudo systemctl restart shadowbox
```

The service now declares `Wants=pigpiod.service` and `After=pigpiod.service`, so
Shadowbox will wait for pigpio during boot.

---

## Shadowbox logs

View runtime logs:

```
journalctl -u shadowbox -f
```
