**Shadowbox**

Hardware UI for Cycling ’74 RNBO Runner on Raspberry Pi.

Shadowbox provides a patch browser and parameter editor using a rotary encoder and OLED display, allowing RNBO patches exported from Max to be loaded and edited directly from hardware without using the RNBO Runner web interface.

Shadowbox communicates with RNBO Runner via OSC and OSCQuery, automatically discovering:
	•	available patches
	•	parameters
	•	system status

This enables a standalone embedded workflow for RNBO-based instruments.

⸻

Features
	•	Patch browsing and loading
	•	Parameter editing via rotary encoder
	•	OLED UI (SSD1306 I²C)
	•	Automatic patch discovery via OSCQuery
	•	RNBO parameter introspection
	•	Audio interface selection
	•	System status display (CPU / xruns)
	•	Persistent state across reboots
	•	Startup splash screen
	•	Activity indicator during refresh/load
	•	Runs automatically via systemd service

⸻

**Hardware**

Shadowbox currently targets a Raspberry Pi 4 / 5.

Typical components:

Rotary Encoder
Example: EC11 detented encoder

OLED Display
Example: SSD1306 128×32 I²C

Interface
GPIO + I²C

Typical Wiring

Encoder A → GPIO17
Encoder B → GPIO27
Encoder Switch → GPIO22

OLED SDA → GPIO2
OLED SCL → GPIO3

More details are available in:

docs/wiring.md

⸻

**Software Requirements**

Recommended OS:

Raspberry Pi OS Bookworm

Required Python libraries:

pigpio
python-osc
smbus2

Install system dependencies:

sudo apt install pigpio python3-pigpio python3-smbus python3-pip

Enable the pigpio daemon:

sudo systemctl enable pigpiod
sudo systemctl start pigpiod

⸻

**Installation**

Clone the repository

git clone https://github.com/YOURNAME/shadowbox.git
cd shadowbox

Create a virtual environment

python3 -m venv .venv
source .venv/bin/activate

Install Python dependencies

pip install -r requirements.txt

Run Shadowbox

python shadowbox.py

⸻

**Running at Boot (systemd)**

Shadowbox can run automatically when the Raspberry Pi boots.

Install the systemd service

sudo cp service/shadowbox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shadowbox
sudo systemctl start shadowbox

Check service status

systemctl status shadowbox

⸻

**Usage**

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

⸻

**Patch Browser**

Shadowbox automatically discovers patches exported to RNBO Runner.

Selecting a patch sends the OSC message

/rnbo/inst/control/load

to RNBO Runner.

⸻

**Parameter Editing**

Parameters are discovered through OSCQuery and displayed on the OLED.

Editing a parameter sends OSC messages directly to the RNBO parameter path.

Example parameter path

/rnbo/inst/0/params/root

⸻

**System Menu**

STATUS
AUDIO
NETWORK
STARTUP
MAINT

Capabilities include:
	•	audio interface selection
	•	JACK restart
	•	startup patch control
	•	CPU / xrun monitoring

⸻

**Architecture**

Shadowbox is built with a modular architecture separating UI, rendering, hardware input, and RNBO communication.

shadowbox.py
Main orchestration loop

ui.py
UI state machine

renderer.py
OLED layout and drawing logic

display.py
SSD1306 display driver

encoder.py
Rotary encoder hardware input

rnbo.py
OSC and OSCQuery communication with RNBO Runner

Dependency flow:

shadowbox → ui → renderer / rnbo / encoder / display

Design goals:
	•	deterministic UI behavior
	•	minimal coupling
	•	clean hardware abstraction
	•	separation between UI logic and rendering

More details are available in:

docs/architecture.md

⸻

**Tools**

Utility programs are located in the tools directory.

Example:

encoder_test.py

This program can be used to verify encoder wiring and behavior.

⸻

**Development Workflow**

Typical workflow:
	1.	Export RNBO patch from Max
	2.	Copy export to the RNBO Runner directory
	3.	Shadowbox automatically discovers the patch
	4.	Load the patch from the hardware interface
	5.	Edit parameters directly from the encoder

No browser interaction is required.

⸻

**Repository Structure**

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

⸻

**Roadmap**

Planned improvements:
	•	improved encoder acceleration
	•	parameter scaling hints
	•	richer parameter display
	•	multi-column UI layout
	•	patch metadata support
	•	patch tagging and grouping
	•	deeper RNBO system integration

⸻

License

MIT License

⸻

Acknowledgments

Shadowbox builds on Cycling ’74 RNBO and the RNBO Runner project.

Cycling ’74 RNBO
https://cycling74.com/products/rnbo
