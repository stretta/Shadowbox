#!/usr/bin/env python3

import sys
from pathlib import Path
import time

# add repo root to python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shadowbox.display import SSD1306Display

d = SSD1306Display()
d.init()

# clear screen
d.clear()
d.show()

# draw test text
d.text("SHADOWBOX", 20, 8)
d.text("display OK", 20, 20)
d.show()

print("Display test running. Ctrl+C to exit.")

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    d.clear()
    d.show()
