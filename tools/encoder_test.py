#!/usr/bin/env python3

import os
import pigpio
import time

CLK = int(os.environ.get("SHADOWBOX_ENCODER_CLK", "17"), 0)
DT = int(os.environ.get("SHADOWBOX_ENCODER_DT", "27"), 0)
SW = int(os.environ.get("SHADOWBOX_ENCODER_SW", "22"), 0)
BACK = int(os.environ.get("SHADOWBOX_BACK_BUTTON_PIN", "0"), 0)

STEPS_PER_DETENT = int(os.environ.get("SHADOWBOX_ENCODER_STEPS_PER_DETENT", "4"), 0)
AB_GLITCH_US = int(os.environ.get("SHADOWBOX_ENCODER_AB_GLITCH_US", "0"), 0)
SW_GLITCH_US = int(os.environ.get("SHADOWBOX_ENCODER_SW_GLITCH_US", "8000"), 0)
ACCEL_FAST_SECONDS = float(os.environ.get("SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS", "0.35"))
ACCEL_FAST_MULTIPLIER = int(os.environ.get("SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER", "2"), 0)
ACCEL_TURBO_SECONDS = float(os.environ.get("SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS", "0.018"))
ACCEL_TURBO_MULTIPLIER = int(os.environ.get("SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER", "3"), 0)

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

button_pins = [CLK, DT, SW]
if BACK > 0 and BACK not in button_pins:
    button_pins.append(BACK)

for pin in button_pins:
    pi.set_mode(pin, pigpio.INPUT)
    pi.set_pull_up_down(pin, pigpio.PUD_UP)

pi.set_glitch_filter(CLK, AB_GLITCH_US)
pi.set_glitch_filter(DT, AB_GLITCH_US)
pi.set_glitch_filter(SW, SW_GLITCH_US)
if BACK > 0:
    pi.set_glitch_filter(BACK, int(os.environ.get("SHADOWBOX_BACK_BUTTON_GLITCH_US", "0"), 0))


def read_ab():
    a = pi.read(CLK)
    b = pi.read(DT)
    return (a << 1) | b


state = read_ab()
accum = 0
last_detent_at = None


def on_ab(gpio, level, tick):
    global state, accum, last_detent_at

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
        now = time.monotonic()
        scale = 1
        if last_detent_at is not None:
            elapsed = now - last_detent_at
            if ACCEL_TURBO_SECONDS > 0 and elapsed <= ACCEL_TURBO_SECONDS:
                scale = ACCEL_TURBO_MULTIPLIER
            elif ACCEL_FAST_SECONDS > 0 and elapsed <= ACCEL_FAST_SECONDS:
                scale = ACCEL_FAST_MULTIPLIER
        last_detent_at = now
        print(f"CW +{scale}")

    elif accum <= -STEPS_PER_DETENT:
        accum += STEPS_PER_DETENT
        now = time.monotonic()
        scale = 1
        if last_detent_at is not None:
            elapsed = now - last_detent_at
            if ACCEL_TURBO_SECONDS > 0 and elapsed <= ACCEL_TURBO_SECONDS:
                scale = ACCEL_TURBO_MULTIPLIER
            elif ACCEL_FAST_SECONDS > 0 and elapsed <= ACCEL_FAST_SECONDS:
                scale = ACCEL_FAST_MULTIPLIER
        last_detent_at = now
        print(f"CCW -{scale}")


cb_a = pi.callback(CLK, pigpio.EITHER_EDGE, on_ab)
cb_b = pi.callback(DT, pigpio.EITHER_EDGE, on_ab)


last_sw = 1
last_back = 1

print("Encoder test running")
print(f"pins: clk={CLK} dt={DT} sw={SW} back={BACK if BACK > 0 else 'disabled'}")
print(f"steps_per_detent={STEPS_PER_DETENT} ab_glitch_us={AB_GLITCH_US} sw_glitch_us={SW_GLITCH_US}")
print(
    "accel:"
    f" fast<={ACCEL_FAST_SECONDS:.3f}s x{ACCEL_FAST_MULTIPLIER}"
    f" turbo<={ACCEL_TURBO_SECONDS:.3f}s x{ACCEL_TURBO_MULTIPLIER}"
)
print("Use controls or press button\n")

try:
    while True:

        sw = pi.read(SW)

        if sw != last_sw:
            last_sw = sw

            if sw == 0:
                print("SW pressed")
            else:
                print("SW released")

        if BACK > 0:
            back = pi.read(BACK)
            if back != last_back:
                last_back = back
                if back == 0:
                    print("BACK long_press")
                else:
                    print("BACK released")

        time.sleep(0.01)

except KeyboardInterrupt:
    pass

finally:
    cb_a.cancel()
    cb_b.cancel()
    pi.stop()
