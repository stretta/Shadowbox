# Shadowbox

Shadowbox is a hardware UI for RNBO Runner designed for Raspberry Pi systems running RNBO exports.

https://youtu.be/jnyWAzZjSOs

It provides:

- Instance browsing
- Instance lifecycle control
- Parameter editing
- Preset loading
- Audio and MIDI routing
- Basic system management
- Saved audio-device selection
- Startup discovery/status screen
- Display interface for SSD1306, SSD1309, generic ST7789, Waveshare 1.44-inch LCD HAT, Waveshare 2-inch ST7789V, and Waveshare 5-inch DSI hardware
- Rotary encoder or Waveshare HAT navigation
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
- 240x320 SPI TFT display (generic ST7789, library-backed or raw backend)
- Waveshare 1.44-inch LCD HAT (ST7735S, 128x128 SPI)
- Waveshare 2-inch LCD Module (ST7789V, 240x320 SPI)
- Waveshare 5-inch DSI LCD (800x480 framebuffer)

Current Waveshare 1.44-inch LCD HAT support includes:

- dedicated `st7735s_hat` backend
- hardware-calibrated fixed panel orientation
- joystick + `KEY1`/`KEY2`/`KEY3` input support
- compact text-first `128x128` renderer tuned around a 4-line layout
- simplified startup splash that just shows `SHADOWBOX`

Supported display backends in code:

- `ssd1306`
- `ssd1309`
- `st7789`
- `st7789_raw`
- `st7735s_hat`
- `waveshare_2inch`
- `waveshare_5inch_dsi`

If `SHADOWBOX_DISPLAY` is not set, Shadowbox now defaults to `st7789_raw`.

Example OLED module:

https://www.adafruit.com/product/4484

---

# Features

- Instance browsing from RNBO Runner
- Add instance from published patcher list
- Replace or remove an existing instance when the backend publishes those commands
- Parameter editing
- Graphical value feedback
- Display dim/sleep management
- Encoder navigation
- RNBO OSCQuery integration
- `NEW GRAPH` support when implemented as loading a published set named `New Graph`
- Graph set load/save from published Runner capabilities
- Graph startup configuration through published Runner controls
- System status display
- Direct Ethernet rescue setup with a fixed fallback IP on `eth0`
- Audio device switching
- JACK restart
- Saved top-level cursor and audio-device selection in `~/rnbo-ui/shadowbox_state.json`

Shadowbox treats the published live OSCQuery runtime tree as the source of truth.
It does not maintain its own graph model or restore graph/session state from local persistence.
Graph load/save/startup behavior is executed only through Runner-published set and startup controls.
A curated `NEW GRAPH` action is acceptable when it maps directly to the published set load path using a verified set named `New Graph`.
The `SYSTEM -> NETWORK` screen also includes a local direct-Ethernet setup action that can assign a predictable fallback IP for headless rescue connections.

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

If you plan to use `./install.sh`, it will also enable the required interfaces
for you with noninteractive `raspi-config` calls:

- `ssd1306` / `ssd1309`: enables I2C and SPI
- `st7789` / `st7789_raw` / `waveshare_2inch`: enables SPI and skips I2C setup
- `waveshare_5inch_dsi`: skips both I2C and SPI setup; configure the DSI overlay in `/boot/firmware/config.txt`

You can still do the interface setup manually first if you prefer.

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
fontconfig \
libopenjp2-7 \
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
sudo apt-mark hold rnbooscquery
```

This keeps `apt` from replacing the pinned `rnbooscquery` version during a later upgrade.

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

# 6. Choose setup path

After cloning, you typically have two options:

- For development, testing, or running Shadowbox manually from the checkout,
  continue with the virtual environment steps below.
- For a normal device install that should set up dependencies, hardware
  interfaces, and the systemd service for you, skip ahead to step 11 and run
  `./install.sh`.

---

# 7. Create Python virtual environment

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
pip install --upgrade pip
pip install -r requirements.txt
```

Install test dependencies:

```
pip install -r requirements-dev.txt
```

Run the test suite:

```
python -m pytest
```

Run a focused test file:

```
python -m pytest tests/test_tft_text.py
```

Run Shadowbox directly:

```
python -m shadowbox.shadowbox
```

On TFT builds, export the display backend first or Shadowbox will fall back to
the default raw TFT backend (`st7789_raw`) if you leave `SHADOWBOX_DISPLAY`
unset. OLED builds still use `/dev/i2c-1`.

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

Waveshare 1.44-inch LCD HAT example:

```
export SHADOWBOX_DISPLAY=st7735s_hat
python -m shadowbox.shadowbox
```

Use `waveshare_2inch` instead if that matches your display wiring.

Waveshare 5-inch DSI LCD example:

```
export SHADOWBOX_DISPLAY=waveshare_5inch_dsi
python -m shadowbox.shadowbox
```

This backend writes Shadowbox frames to the Linux framebuffer, `/dev/fb0` by
default, and controls brightness through `/sys/class/backlight` when the OS
exposes it. The DSI panel itself must already be enabled by the Raspberry Pi OS
display overlay. The 5-inch renderer uses the full 800x480 logical framebuffer
by default; only set `SHADOWBOX_LOGICAL_WIDTH` and `SHADOWBOX_LOGICAL_HEIGHT`
when you intentionally want scaled compatibility output. Waveshare's setup for
the 800x480 DSI panel uses:

```
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-7inch
```

On Pi 5 or CM4/CM3 systems using DSI0 instead of DSI1, use the matching overlay
variant:

```
dtoverlay=vc4-kms-dsi-7inch,dsi0
```

If the framebuffer is not `/dev/fb0`, set `SHADOWBOX_DSI_FRAMEBUFFER`. If your
OS exposes a non-default framebuffer pixel layout, set
`SHADOWBOX_DSI_PIXEL_FORMAT` to `bgrx8888`, `rgbx8888`, `rgb565`, or `rgb888`.

If `pigpiod` is not running, startup will fail with `RuntimeError: pigpio daemon not running`.

---

# 8. Test display

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

For the Waveshare 1.44-inch LCD HAT, use the dedicated backend:

```
SHADOWBOX_DISPLAY=st7735s_hat python -m shadowbox.shadowbox
```

To verify the panel without starting the full app:

```
python -m tools.st7735s_hat_test
```

---

# 9. Test controls

Run:

```
python -m tools.encoder_test
```

Encoder builds should print step values from the knob. Waveshare 1.44-inch LCD HAT builds should print step/press events from the joystick and keys.

---

# 10. Controls + display test

Run:

```
python -m tools.encoder_display_test
```

The current control input should update the display test UI.

---

# 11. Install the Shadowbox service

From the repository root:

```
./install.sh
```

Do not run the installer with `sudo`. Run it as your normal user from the
repository root and let it prompt for `sudo` only when needed.

The installer checks `SHADOWBOX_DISPLAY` to decide whether I2C setup is needed.
For TFT and DSI builds, export the display backend before running it so the
installer can skip OLED/I2C setup:

```
export SHADOWBOX_DISPLAY=st7789_raw
./install.sh
```

This installs the service:

```
shadowbox.service
```

The installer:

- runs `apt update`
- installs the required system packages
- enables I2C automatically for OLED backends
- enables SPI automatically for SPI display backends
- suppresses Raspberry Pi firmware splash, Plymouth graphics, kernel boot log,
  and systemd status output on the touch display so Shadowbox owns the visible
  boot screen
- enables and starts `pigpiod`
- creates the virtual environment as your current user
- upgrades `pip` and installs `requirements.txt`
- persists the current `SHADOWBOX_*` environment variables to `/etc/default/shadowbox`
- configures passwordless `sudo` for the direct Ethernet helper script
- generates a systemd unit for the current repository path and current user
- reloads systemd, enables `shadowbox`, and restarts the service

It uses `sudo` only for system package, hardware interface, and service steps.
If the installer changes I2C or SPI state on a fresh system, a reboot is still
recommended afterward.
If you exported `SHADOWBOX_DISPLAY` before running `./install.sh`, that value is
saved for future boots in `/etc/default/shadowbox`.

The repository also includes a static unit file at:

```
service/shadowbox.service
```

That file is a template for `/home/pi/Shadowbox`. If your checkout lives elsewhere, either use `./install.sh` or update the unit before installing it manually.

Display selection is controlled through environment variables. The service reads an optional config file at:

```
/etc/default/shadowbox
```

All currently supported `/etc/default/shadowbox` settings:

- General UI/runtime: `SHADOWBOX_POST_LOAD_VIEW`, `SHADOWBOX_TURBO_FPS`, `SHADOWBOX_BRICK_PANEL_FPS`
- Direct Ethernet rescue: `SHADOWBOX_DIRECT_ETHERNET_HELPER`, `SHADOWBOX_DIRECT_ETHERNET_IFACE`, `SHADOWBOX_DIRECT_ETHERNET_CIDR`
- Idle/backlight: `SHADOWBOX_DIM_TIMEOUT`, `SHADOWBOX_SLEEP_TIMEOUT`, `SHADOWBOX_BRIGHTNESS_NORMAL`, `SHADOWBOX_BRIGHTNESS_DIM`
- Encoder/buttons/touch: `SHADOWBOX_INPUT_KIND`, `SHADOWBOX_ENCODER_CLK`, `SHADOWBOX_ENCODER_DT`, `SHADOWBOX_ENCODER_SW`, `SHADOWBOX_BACK_BUTTON_PIN`, `SHADOWBOX_ENCODER_STEPS_PER_DETENT`, `SHADOWBOX_ENCODER_LONG_PRESS_SECONDS`, `SHADOWBOX_ENCODER_AB_GLITCH_US`, `SHADOWBOX_ENCODER_SW_GLITCH_US`, `SHADOWBOX_BACK_BUTTON_GLITCH_US`, `SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS`, `SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER`, `SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS`, `SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER`, `SHADOWBOX_HAT_JOY_UP`, `SHADOWBOX_HAT_JOY_DOWN`, `SHADOWBOX_HAT_JOY_LEFT`, `SHADOWBOX_HAT_JOY_RIGHT`, `SHADOWBOX_HAT_JOY_PRESS`, `SHADOWBOX_HAT_KEY1`, `SHADOWBOX_HAT_KEY2`, `SHADOWBOX_HAT_KEY3`, `SHADOWBOX_HAT_KEY1_ACTION`, `SHADOWBOX_HAT_KEY2_ACTION`, `SHADOWBOX_HAT_KEY3_ACTION`, `SHADOWBOX_TOUCH_DEVICE`, `SHADOWBOX_TOUCH_WIDTH`, `SHADOWBOX_TOUCH_HEIGHT`
- OLED backends (`ssd1306`, `ssd1309`): `SHADOWBOX_DISPLAY`, `SHADOWBOX_I2C_BUS`, `SHADOWBOX_I2C_ADDR`
- Generic ST7789 backends (`st7789`, `st7789_raw`): `SHADOWBOX_DISPLAY`, `SHADOWBOX_ST7789_SPI_BUS`, `SHADOWBOX_ST7789_SPI_CS`, `SHADOWBOX_ST7789_DC`, `SHADOWBOX_ST7789_RST`, `SHADOWBOX_ST7789_BACKLIGHT`, `SHADOWBOX_ST7789_SPI_SPEED_HZ`, `SHADOWBOX_ST7789_ROTATION`, `SHADOWBOX_ST7789_WIDTH`, `SHADOWBOX_ST7789_HEIGHT`, `SHADOWBOX_ST7789_OFFSET_LEFT`, `SHADOWBOX_ST7789_OFFSET_TOP`, `SHADOWBOX_ST7789_INVERT`, `SHADOWBOX_LOGICAL_WIDTH`, `SHADOWBOX_LOGICAL_HEIGHT`
- Waveshare 1.44-inch LCD HAT backend (`st7735s_hat`): `SHADOWBOX_DISPLAY`, `SHADOWBOX_ST7735_SPI_BUS`, `SHADOWBOX_ST7735_SPI_CS`, `SHADOWBOX_ST7735_DC`, `SHADOWBOX_ST7735_RST`, `SHADOWBOX_ST7735_BACKLIGHT`, `SHADOWBOX_ST7735_SPI_SPEED_HZ`, `SHADOWBOX_ST7735_WIDTH`, `SHADOWBOX_ST7735_HEIGHT`, `SHADOWBOX_ST7735_OFFSET_LEFT`, `SHADOWBOX_ST7735_OFFSET_TOP`, `SHADOWBOX_ST7735_INVERT`, `SHADOWBOX_LOGICAL_WIDTH`, `SHADOWBOX_LOGICAL_HEIGHT`
- Waveshare 2-inch backend (`waveshare_2inch`): `SHADOWBOX_DISPLAY`, `SHADOWBOX_WAVESHARE_SPI_BUS`, `SHADOWBOX_WAVESHARE_SPI_CS`, `SHADOWBOX_WAVESHARE_DC`, `SHADOWBOX_WAVESHARE_RST`, `SHADOWBOX_WAVESHARE_BACKLIGHT`, `SHADOWBOX_WAVESHARE_SPI_SPEED_HZ`, `SHADOWBOX_LOGICAL_WIDTH`, `SHADOWBOX_LOGICAL_HEIGHT`
- Waveshare 5-inch DSI backend (`waveshare_5inch_dsi`): `SHADOWBOX_DISPLAY`, `SHADOWBOX_DSI_FRAMEBUFFER`, `SHADOWBOX_DSI_WIDTH`, `SHADOWBOX_DSI_HEIGHT`, `SHADOWBOX_DSI_PIXEL_FORMAT`, `SHADOWBOX_DSI_BACKLIGHT_PATH`, `SHADOWBOX_LOGICAL_WIDTH`, `SHADOWBOX_LOGICAL_HEIGHT`

Notes:

- `SHADOWBOX_DISPLAY` defaults to `st7789_raw` if unset.
- `SHADOWBOX_INPUT_KIND=touch_zones` maps top-left to back, top-right to enter, bottom-left to previous, and bottom-right to next.
- `SHADOWBOX_INPUT_KIND=touch_direct` enables the first-pass direct-touch action model for the 5-inch prototype. It emits semantic actions (`tap_row`, `tap_back`, `tap_button`, `page_up`, `page_down`) and enables the touch layout/hit-target renderer. `waveshare_5inch_dsi` defaults to this input mode unless `SHADOWBOX_INPUT_KIND` is set explicitly.
- `SHADOWBOX_BRICK_PANEL_FPS` is a legacy fallback for `SHADOWBOX_TURBO_FPS`.
- `SHADOWBOX_ST7789_RST`, `SHADOWBOX_ST7789_BACKLIGHT`, and `SHADOWBOX_WAVESHARE_BACKLIGHT` accept `none` to disable that pin.
- `SHADOWBOX_ST7735_RST` and `SHADOWBOX_ST7735_BACKLIGHT` accept `none` to disable that pin.
- `SHADOWBOX_ST7789_INVERT` accepts boolean-style values such as `1`, `true`, `yes`, or `on`.
- `SHADOWBOX_ST7735_INVERT` accepts boolean-style values such as `1`, `true`, `yes`, or `on`.

You can also choose where Shadowbox lands after loading or replacing an instance:

```
SHADOWBOX_POST_LOAD_VIEW=instance
```

Supported values:

- `instance` keeps the current behavior and returns to the instance menu
- `parameters` jumps straight into the parameter list for the loaded instance
- `presets` jumps straight into the preset list for the loaded instance

Shadowbox also has a shared turbo render cadence for animation-heavy screens:

```
SHADOWBOX_TURBO_FPS=40
```

This is separate from the base UI frame rate and only applies to screens that
explicitly opt in. Right now, Brick Panel is the only turbo-rendered screen.
For compatibility, the older `SHADOWBOX_BRICK_PANEL_FPS` name is still accepted
as a fallback, but new configs should prefer `SHADOWBOX_TURBO_FPS`.

For dim/sleep testing, you can override the idle behavior in `/etc/default/shadowbox`:

```
SHADOWBOX_DIM_TIMEOUT=3
SHADOWBOX_SLEEP_TIMEOUT=6
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

That makes the display dim after 3 seconds of no encoder activity and sleep after 6 seconds. On TFT/DSI backends, use `255/64`-style brightness values rather than OLED-style `127/16`, or the display can look dim immediately at startup.

Example ST7789 configuration:

```
SHADOWBOX_DISPLAY=st7789
SHADOWBOX_ST7789_SPI_BUS=0
SHADOWBOX_ST7789_SPI_CS=0
SHADOWBOX_ST7789_DC=9
SHADOWBOX_ST7789_RST=13
SHADOWBOX_ST7789_BACKLIGHT=19
SHADOWBOX_ST7789_SPI_SPEED_HZ=80000000
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
SHADOWBOX_ST7789_SPI_SPEED_HZ=40000000
SHADOWBOX_ST7789_ROTATION=0
SHADOWBOX_ST7789_WIDTH=320
SHADOWBOX_ST7789_HEIGHT=240
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
SHADOWBOX_ST7789_INVERT=0
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

For touch input on the 5-inch panel, Shadowbox defaults to
`SHADOWBOX_INPUT_KIND=touch_direct`. Set `SHADOWBOX_TOUCH_DEVICE` if automatic
touchscreen discovery picks the wrong `/dev/input/event*` device. The
diagnostic helpers `tools/touch_test.py` and `tools/touch_raw_test.py` can be
used to confirm normalized touch events before running the full UI.

Example Waveshare 1.44-inch LCD HAT configuration:

```
SHADOWBOX_DISPLAY=st7735s_hat
SHADOWBOX_ST7735_SPI_BUS=0
SHADOWBOX_ST7735_SPI_CS=0
SHADOWBOX_ST7735_DC=25
SHADOWBOX_ST7735_RST=27
SHADOWBOX_ST7735_BACKLIGHT=24
SHADOWBOX_ST7735_SPI_SPEED_HZ=20000000
SHADOWBOX_ST7735_WIDTH=128
SHADOWBOX_ST7735_HEIGHT=128
SHADOWBOX_ST7735_OFFSET_LEFT=2
SHADOWBOX_ST7735_OFFSET_TOP=3
SHADOWBOX_LOGICAL_WIDTH=128
SHADOWBOX_LOGICAL_HEIGHT=128
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Known-good Raspberry Pi config:

`<pi-host>`, raw ST7789 backend, `/home/pi/Shadowbox`

```sh
SHADOWBOX_DISPLAY=st7789_raw
SHADOWBOX_ST7789_SPI_BUS=0
SHADOWBOX_ST7789_SPI_CS=0
SHADOWBOX_ST7789_DC=25
SHADOWBOX_ST7789_RST=24
SHADOWBOX_ST7789_BACKLIGHT=18
SHADOWBOX_ST7789_SPI_SPEED_HZ=40000000
SHADOWBOX_ST7789_ROTATION=0
SHADOWBOX_ST7789_WIDTH=320
SHADOWBOX_ST7789_HEIGHT=240
SHADOWBOX_ST7789_OFFSET_LEFT=0
SHADOWBOX_ST7789_OFFSET_TOP=0
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
SHADOWBOX_ST7789_INVERT=0
SHADOWBOX_ENCODER_CLK=17
SHADOWBOX_ENCODER_DT=27
SHADOWBOX_ENCODER_SW=22
SHADOWBOX_BACK_BUTTON_PIN=23
SHADOWBOX_BACK_BUTTON_GLITCH_US=0
SHADOWBOX_DIM_TIMEOUT=120
SHADOWBOX_SLEEP_TIMEOUT=600
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Deploy to a Pi:

```bash
PI_HOST=<pi-host>
ssh "pi@$PI_HOST" "mkdir -p /home/pi/Shadowbox" && \
rsync -av --delete --progress \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  /Users/mdavidson/Documents/Repos/Shadowbox/ \
  "pi@$PI_HOST:/home/pi/Shadowbox/"
```

Restart Shadowbox on the Pi:

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
SHADOWBOX_WAVESHARE_SPI_SPEED_HZ=40000000
SHADOWBOX_LOGICAL_WIDTH=320
SHADOWBOX_LOGICAL_HEIGHT=240
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Example Waveshare 5-inch DSI configuration:

```
SHADOWBOX_DISPLAY=waveshare_5inch_dsi
SHADOWBOX_DSI_FRAMEBUFFER=/dev/fb0
SHADOWBOX_DSI_WIDTH=800
SHADOWBOX_DSI_HEIGHT=480
SHADOWBOX_DSI_PIXEL_FORMAT=auto
SHADOWBOX_LOGICAL_WIDTH=800
SHADOWBOX_LOGICAL_HEIGHT=480
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Example Waveshare 1.44-inch LCD HAT configuration:

```
SHADOWBOX_DISPLAY=st7735s_hat
SHADOWBOX_ST7735_SPI_BUS=0
SHADOWBOX_ST7735_SPI_CS=0
SHADOWBOX_ST7735_DC=25
SHADOWBOX_ST7735_RST=27
SHADOWBOX_ST7735_BACKLIGHT=24
SHADOWBOX_ST7735_WIDTH=128
SHADOWBOX_ST7735_HEIGHT=128
SHADOWBOX_ST7735_OFFSET_LEFT=2
SHADOWBOX_ST7735_OFFSET_TOP=3
SHADOWBOX_ST7735_INVERT=true
SHADOWBOX_HAT_JOY_UP=6
SHADOWBOX_HAT_JOY_DOWN=19
SHADOWBOX_HAT_JOY_LEFT=5
SHADOWBOX_HAT_JOY_RIGHT=26
SHADOWBOX_HAT_JOY_PRESS=13
SHADOWBOX_HAT_KEY1=21
SHADOWBOX_HAT_KEY2=20
SHADOWBOX_HAT_KEY3=16
SHADOWBOX_HAT_KEY1_ACTION=long_press
SHADOWBOX_HAT_KEY2_ACTION=short_press
SHADOWBOX_HAT_KEY3_ACTION=none
SHADOWBOX_BRIGHTNESS_NORMAL=255
SHADOWBOX_BRIGHTNESS_DIM=64
```

Notes for the Waveshare 1.44-inch LCD HAT:

- Shadowbox now uses a hardware-calibrated fixed panel mapping for this HAT. There is no `SHADOWBOX_ST7735_ROTATION` setting anymore.
- The `st7735s_hat` renderer is intentionally text-first and uses a compact 4-line `128x128` layout instead of the larger TFT card/icon treatment.
- The startup screen on this HAT is a simple `SHADOWBOX` splash rather than the denser TFT startup status block.

On Raspberry Pi Bookworm, Waveshare also recommends enabling pull-ups for the
HAT buttons in `/boot/firmware/config.txt`:

```
gpio=6,19,5,26,13,21,20,16=pu
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
SHADOWBOX_ENCODER_AB_GLITCH_US=0
SHADOWBOX_ENCODER_SW_GLITCH_US=8000
SHADOWBOX_BACK_BUTTON_GLITCH_US=0
SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS=0.35
SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER=2
SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS=0.018
SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER=3
```

Lower `STEPS_PER_DETENT` makes one click register sooner. Higher `AB_GLITCH_US`
filters more bounce but can make the knob feel heavier. The acceleration values
now apply to float-style parameter editing only, so fast turns can sweep wide
ranges without making lists and discrete editors jump unpredictably.
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

If `SHADOWBOX_DISPLAY` is not set, Shadowbox now defaults to `st7789_raw`.

Parameter metadata is documented in [docs/uispec.md](./docs/uispec.md) and
[docs/walkthrough.md](./docs/walkthrough.md). Supported parameter/UI metadata
keys currently include `editor`, `unit`, `units`, `display_precision`,
`display_as`, `edit_step`, `edit_as`, `bool`, `is_bool`, `boolean`,
`playhead_state`, `pitch_state`, `cents_state`, and `ui_role`.

---

# 12. Update Shadowbox

If Shadowbox is already installed on the Pi and you want to update it to the
latest version from this repository, use one of these paths.

Update directly on the Pi checkout:

```bash
cd ~/Shadowbox
git pull
source .venv/bin/activate
pip install -r requirements.txt
./install.sh
```

Why rerun `./install.sh` after pulling:

- it refreshes system packages if new ones were added
- it updates the Python virtual environment
- it rewrites the systemd unit for the current checkout path and user
- it refreshes the direct Ethernet helper sudoers entry
- it preserves existing `/etc/default/shadowbox` settings and only updates
  `SHADOWBOX_*` variables you exported before running it
- it restarts the `shadowbox` service

If you changed local files in the Pi checkout, `git pull` may stop with merge
conflicts. In that case, either commit/stash those changes first or deploy a
fresh copy from your development machine with the helper below.

Update from your Mac or development machine with the deploy helper:

```bash
PI_HOST=<pi-host> tools/deploy_pi.sh
```

Useful variants:

- `tools/deploy_pi.sh --dry-run` previews the sync
- `tools/deploy_pi.sh --sync-only` copies files without reinstalling Python
  requirements or restarting the service
- `PI_HOST=<pi-host> tools/deploy_pi.sh --no-install-deps` is useful when only
  app code changed and dependencies did not
- `tools/deploy_pi.sh --alias studio --no-install-deps` does the same thing when
  you prefer a configured alias

After either update path, verify the service:

```bash
systemctl status shadowbox --no-pager -l
```

---

# 13. Start the service

```
sudo systemctl start shadowbox
```

Check status:

```
systemctl status shadowbox
```

---

# 14. Enable auto-start

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
PI_HOST=<pi-host> tools/deploy_pi.sh
tools/deploy_pi.sh --dry-run
tools/deploy_pi.sh --sync-only
PI_HOST=<pi-host> tools/deploy_pi.sh --no-install-deps
tools/deploy_pi.sh --alias studio --no-install-deps
```

Built-in aliases currently include `pt4`, `studio`, and `bench`. Run `tools/deploy_pi.sh --help` to see all options.
`--dry-run` still connects to the Pi so `rsync` can compare the remote tree, but it does not change files or restart services.

If an alias maps to a `.local` hostname, the deploy script now tries to resolve it to an IP before connecting. When mDNS is unavailable on your Mac, either pass the IP directly:

```bash
tools/deploy_pi.sh --host 192.168.68.123
```

or set a per-alias override:

```bash
export PI_HOST_ALIAS_PT4=192.168.68.123
tools/deploy_pi.sh --alias pt4
```

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
├── requirements-dev.txt
├── requirements.txt
├── README.md
├── service/
│   └── shadowbox.service
├── shadowbox/
│   ├── __init__.py
│   ├── brick_panel.py
│   ├── data/
│   ├── display/
│   │   └── waveshare_5inch_dsi.py
│   ├── editors/
│   ├── encoder.py
│   ├── midi_mappings.py
│   ├── renderer.py
│   ├── rnbo.py
│   ├── shadowbox.py
│   ├── touch.py
│   ├── ui.py
│   └── version.py
├── tests/
│   ├── test_brick_panel.py
│   ├── test_display_defaults.py
│   ├── test_encoder_input.py
│   ├── test_instance_actions.py
│   ├── test_param_metadata.py
│   ├── test_pitch_display.py
│   ├── test_step16_renderer.py
│   ├── test_tft_text.py
│   ├── test_touch_direct_ui.py
│   ├── test_touch_zones.py
│   ├── test_ttid_renderer.py
│   ├── test_waveshare_5inch_dsi.py
│   └── test_version.py
└── tools/
    ├── deploy_pi.sh
    ├── display_test.py
    ├── encoder_display_test.py
    ├── encoder_test.py
    ├── rnbo_runner_presets_to_maxsnap.py
    ├── st7789_raw_test.py
    ├── st7789_test.py
    ├── touch_raw_test.py
    └── touch_test.py
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
