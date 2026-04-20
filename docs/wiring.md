Encoder wiring

Encoder → Raspberry Pi

CLK → GPIO17
DT  → GPIO27
SW  → GPIO22
BACK → optional GPIO5
GND → GND
VCC → 3.3V

Waveshare 2-inch TFT variant

CLK → GPIO17
DT  → GPIO26
SW  → GPIO22
BACK → optional GPIO5
GND → GND
VCC → 3.3V

SSD1306 I2C display

VCC → 3.3V
GND → GND
SDA → GPIO2
SCL → GPIO3

Waveshare 1.44-inch LCD HAT

Display
DC  → GPIO25
RST → GPIO27
BL  → GPIO24
CS  → GPIO8/CE0
MOSI → GPIO10
SCLK → GPIO11

Controls
JOY_UP    → GPIO6
JOY_DOWN  → GPIO19
JOY_LEFT  → GPIO5
JOY_RIGHT → GPIO26
JOY_PRESS → GPIO13
KEY1      → GPIO21
KEY2      → GPIO20
KEY3      → GPIO16

Shadowbox HAT mapping
Joystick up/left   → step -1
Joystick down/right → step +1
Joystick press     → short/long press
KEY1               → long_press back/cancel
KEY2               → short_press confirm shortcut
KEY3               → unused by default
