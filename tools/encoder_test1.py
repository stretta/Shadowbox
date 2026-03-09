#!/usr/bin/env python3

import pigpio
import time

CLK = 17
DT = 27
SW = 22

STEPS_PER_DETENT = 4

# quadrature decode table
TRANS = (
     0, -1, +1,  0,
    +1,  0,  0, -1,
    -1,  0,  0, +1,
     0, +1, -1,  0,
)

pi = pigpio.pi()

if not pi.connected:
    print("pigpio daemon not running")
    exit()

for pin in (CLK, DT, SW):
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_glitch_filter(CLK, 200)
pi.set_glitch_filter(DT, 200)
pi.set_glitch_filter(SW, 8000)


def read_ab():
    a = pi.read(CLK)
    b = pi.read(DT)
    return (a << 1) | b


state = read_ab()
accum = 0


def on_ab(gpio, level, tick):
    global state, accum

    if level == 2:
        return

    new = read_ab()
    move = TRANS[(state << 2) | new]

    state = new

    if move == 0:
        return

    accum += move

    if accum >= STEPS_PER_DETENT:
        accum -= STEPS_PER_DETENT
        print("CW +1")

    elif accum <= -STEPS_PER_DETENT:
        accum += STEPS_PER_DETENT
        print("CCW -1")


cb_a = pi.callback(CLK, pigpio.EITHER_EDGE, on_ab)
cb_b = pi.callback(DT, pigpio.EITHER_EDGE, on_ab)


last_sw = 1

print("Encoder test running")
print("Turn encoder or press button\n")

try:
    while True:

        sw = pi.read(SW)

        if sw != last_sw:
            last_sw = sw

            if sw == 0:
                print("SW pressed")
            else:
                print("SW released")

        time.sleep(0.01)

except KeyboardInterrupt:
    pass

finally:
    cb_a.cancel()
    cb_b.cancel()
    pi.stop()
