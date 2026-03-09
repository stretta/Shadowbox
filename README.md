Shadowbox

Shadowbox is a hardware user interface for Cycling ’74 RNBO Runner running on a Raspberry Pi.

It provides a patch browser and parameter editor using a rotary encoder and OLED display, allowing patches exported from Max/RNBO to be loaded and edited directly from hardware without needing the RNBO Runner web interface.

Shadowbox communicates with RNBO Runner using OSC and OSCQuery and automatically discovers available patches, parameters, and system status.

This enables a standalone embedded workflow for RNBO-based instruments.

Features
	•	Patch browsing and loading
	•	Parameter editing via rotary encoder
	•	OLED UI (SSD1306 I2C)
	•	Automatic patch discovery using OSCQuery
	•	RNBO parameter introspection
	•	Audio interface selection
	•	System status display (CPU / xruns)
	•	Persistent state across reboots
	•	Startup splash screen
	•	Activity indicator during refresh/load
	•	Systemd service for automatic boot

Hardware

Shadowbox currently targets a Raspberry Pi 4 or Raspberry Pi 5.

Typical components:

Rotary encoder
Example: EC11 detented encoder

OLED display
Example: SSD1306 128x32 I2C

Connection
I2C + GPIO

Typical wiring

Encoder A   -> GPIO17
Encoder B   -> GPIO27
Encoder SW  -> GPIO22

OLED SDA    -> GPIO2
OLED SCL    -> GPIO3

See documentation in:

docs/wiring.md

Software Requirements

Raspberry Pi OS (Bookworm recommended)

Required Python libraries

pigpio
python-osc
smbus2

Install system dependencies

sudo apt install pigpio python3-pigpio python3-smbus python3-pip

Start the pigpio daemon

sudo systemctl enable pigpiod
sudo systemctl start pigpiod

Installation

Clone the repository

git clone https://github.com/yourname/shadowbox.git
cd shadowbox

Create a Python virtual environment

python3 -m venv .venv
source .venv/bin/activate

Install Python dependencies

pip install -r requirements.txt

Run Shadowbox

python shadowbox.py

Running at Boot (systemd)

Shadowbox can run automatically when the Raspberry Pi boots.

Install the systemd service

sudo cp service/shadowbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shadowbox
sudo systemctl start shadowbox

Check service status

systemctl status shadowbox

Usage

Encoder Controls

Rotate encoder
Navigate menus

Press encoder
Select / enter

Long press encoder
Escape / go back

Top Level Menus

PATCH
PARAM
SYSTEM

Patch Browser

Shadowbox automatically discovers patches exported to RNBO Runner.

Selecting a patch sends the OSC message

/rnbo/inst/control/load

to RNBO Runner.

Parameter Editing

Parameters are discovered through OSCQuery and displayed on the OLED.

Editing a parameter sends OSC messages directly to the parameter path.

Example parameter path

/rnbo/inst/0/params/root

System Menu

STATUS
AUDIO
NETWORK
STARTUP
MAINT

Capabilities include
	•	audio interface selection
	•	JACK restart
	•	startup patch control
	•	CPU/xrun monitoring

Architecture

Shadowbox is organized into modules with clear responsibilities.

shadowbox.py
Main orchestration loop

ui.py
UI state machine

renderer.py
OLED layout and rendering logic

display.py
SSD1306 OLED display driver

encoder.py
Rotary encoder hardware input

rnbo.py
OSC and OSCQuery communication with RNBO Runner

Dependency structure

shadowbox.py controls the system

ui.py manages state

renderer.py draws the UI

encoder.py provides input

display.py handles hardware drawing

rnbo.py handles network communication

More details are available in

docs/architecture.md

Tools

Utility programs are located in

tools/

Example

encoder_test.py

Used to verify encoder wiring and behavior.

Development Workflow

Typical development workflow
	1.	Export RNBO patch from Max
	2.	Copy export to RNBO Runner directory
	3.	Shadowbox automatically discovers patch
	4.	Load patch from the hardware interface
	5.	Edit parameters directly from the encoder

No browser interaction required.

Repository Structure

shadowbox/

shadowbox.py
ui.py
renderer.py
rnbo.py
display.py
encoder.py

requirements.txt
install.sh
README.md

docs/
architecture.md
wiring.md

service/
shadowbox.service

tools/
encoder_test.py

Roadmap

Possible future improvements
	•	improved encoder acceleration
	•	parameter scaling hints
	•	richer parameter display
	•	multi-column UI layout
	•	patch metadata support
	•	patch tagging and grouping
	•	deeper RNBO system integration

License

MIT License

Acknowledgments

Shadowbox builds on Cycling ’74 RNBO and the RNBO Runner project.

Cycling ’74 RNBO
https://cycling74.com/products/rnbo