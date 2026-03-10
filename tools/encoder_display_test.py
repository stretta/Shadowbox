#!/usr/bin/env python3

import time

import pigpio
from shadowbox.display import SSD1306Display

CLK = 17
DT = 27
SW = 22

STEPS_PER_DETENT = 4

TRANS = (
     0, -1, +1,  0,
    +1,  0,  0, -1,
    -1,  0,  0, +1,
     0, +1, -1,  0,
)


class EncoderDisplayTest:
    def __init__(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("pigpio daemon not running")

        for pin in (CLK, DT, SW):
            self.pi.set_mode(pin, pigpio.INPUT)
            self.pi.set_pull_up_down(pin, pigpio.PUD_UP)

        self.pi.set_glitch_filter(CLK, 200)
        self.pi.set_glitch_filter(DT, 200)
        self.pi.set_glitch_filter(SW, 8000)

        self.display = SSD1306Display()
        self.display.init()

        self.enc_state = self.read_ab()
        self.enc_accum = 0
        self.last_sw = self.pi.read(SW)

        self.last_event = "ready"
        self.position = 0
        self.sw_text = "released"

        self.cb_a = self.pi.callback(CLK, pigpio.EITHER_EDGE, self.on_ab)
        self.cb_b = self.pi.callback(DT, pigpio.EITHER_EDGE, self.on_ab)

    def read_ab(self):
        a = self.pi.read(CLK)
        b = self.pi.read(DT)
        return (a << 1) | b

    def on_ab(self, gpio, level, tick):
        if level == 2:
            return

        new = self.read_ab()
        move = TRANS[(self.enc_state << 2) | new]
        self.enc_state = new

        if move == 0:
            return

        self.enc_accum += move

        if self.enc_accum >= STEPS_PER_DETENT:
            self.enc_accum -= STEPS_PER_DETENT
            self.position += 1
            self.last_event = "CW +1"
            print("CW +1")

        elif self.enc_accum <= -STEPS_PER_DETENT:
            self.enc_accum += STEPS_PER_DETENT
            self.position -= 1
            self.last_event = "CCW -1"
            print("CCW -1")

    def poll_button(self):
        sw = self.pi.read(SW)
        if sw != self.last_sw:
            self.last_sw = sw
            if sw == 0:
                self.sw_text = "pressed"
                self.last_event = "SW press"
                print("SW pressed")
            else:
                self.sw_text = "released"
                self.last_event = "SW release"
                print("SW released")

    def draw(self):
        self.display.clear()
        self.display.text("ENCODER TEST", 0, 0)
        self.display.text(f"event: {self.last_event}"[:21], 0, 10)
        self.display.text(f"pos: {self.position}"[:21], 0, 18)
        self.display.text(f"sw: {self.sw_text}"[:21], 0, 26)
        self.display.show()

    def run(self):
        self.draw()
        print("Encoder+display test running. Ctrl+C to exit.")
        try:
            while True:
                self.poll_button()
                self.draw()
                time.sleep(0.02)
        except KeyboardInterrupt:
            pass
        finally:
            self.cb_a.cancel()
            self.cb_b.cancel()
            self.display.clear()
            self.display.show()
            self.pi.stop()


if __name__ == "__main__":
    EncoderDisplayTest().run()
