#!/usr/bin/env python3

import os
import sys
import time
from pathlib import Path

# add repo root to python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shadowbox.display import SSD1306Display
from shadowbox.encoder import EncoderInput


CLK = int(os.environ.get("SHADOWBOX_ENCODER_CLK", "17"), 0)
DT = int(os.environ.get("SHADOWBOX_ENCODER_DT", "27"), 0)
SW = int(os.environ.get("SHADOWBOX_ENCODER_SW", "22"), 0)
BACK = int(os.environ.get("SHADOWBOX_BACK_BUTTON_PIN", "0"), 0)


class EncoderDisplayTest:
    def __init__(self):
        self.encoder = EncoderInput()
        self.display = SSD1306Display()
        self.display.init()

        self.last_event = "ready"
        self.position = 0
        self.sw_text = "released"
        self.back_text = "disabled" if BACK <= 0 else "released"

    def poll_input(self):
        for event in self.encoder.get_events():
            if event.kind == "rotate":
                self.position += event.delta
                self.last_event = f"CW +{event.delta}" if event.delta > 0 else f"CCW {event.delta}"
                print(self.last_event)
            elif event.kind == "short_press":
                self.sw_text = "short"
                self.last_event = "SW short_press"
                print(self.last_event)
            elif event.kind == "long_press":
                if self.encoder.is_back_button_configured():
                    back_pressed = self.encoder.is_back_button_pressed()
                    if back_pressed:
                        self.back_text = "pressed"
                        self.last_event = "BACK long_press"
                    else:
                        self.sw_text = "long"
                        self.last_event = "SW long_press"
                else:
                    self.sw_text = "long"
                    self.last_event = "SW long_press"
                print(self.last_event)

        if self.sw_text in {"short", "long"} and not self.encoder.is_encoder_button_pressed():
            self.sw_text = "released"

        if self.encoder.is_back_button_configured():
            self.back_text = "pressed" if self.encoder.is_back_button_pressed() else "released"

    def draw(self):
        self.display.clear()
        self.display.text("ENCODER TEST", 0, 0)
        self.display.text(f"event: {self.last_event}"[:21], 0, 10)
        self.display.text(f"pos: {self.position}"[:21], 0, 18)
        status = f"s:{self.sw_text} b:{self.back_text}"
        self.display.text(status[:21], 0, 26)
        self.display.show()

    def run(self):
        self.draw()
        print("Encoder+display test running. Ctrl+C to exit.")
        print(f"pins: clk={CLK} dt={DT} sw={SW} back={BACK if BACK > 0 else 'disabled'}")
        try:
            while True:
                self.poll_input()
                self.draw()
                time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            self.encoder.close()
            self.display.clear()
            self.display.show()


if __name__ == "__main__":
    EncoderDisplayTest().run()
