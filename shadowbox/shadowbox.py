#!/usr/bin/env python3

from __future__ import annotations

from time import monotonic, sleep

from shadowbox.display import SSD1306Display
from shadowbox.encoder import EncoderInput
from shadowbox.rnbo import RNBOClient
from shadowbox.ui import ShadowboxUI
from shadowbox.renderer import ShadowboxRenderer


FPS = 20
FRAME_DT = 1.0 / FPS
REFRESH_SECONDS = 3.0

DIM_TIMEOUT = 120.0
SLEEP_TIMEOUT = 600.0
BRIGHTNESS_NORMAL = 0x7F
BRIGHTNESS_DIM = 0x10


def main():
    display = SSD1306Display()
    display.init()
    display.set_contrast(BRIGHTNESS_NORMAL)

    rnbo = RNBOClient()
    encoder = EncoderInput()
    ui = ShadowboxUI(rnbo=rnbo)
    renderer = ShadowboxRenderer(display=display)

    # Startup splash
    renderer.draw_splash("SHADOWBOX")
    sleep(1.2)

    # Initial discovery
    ui.set_busy(True, "refresh")
    ui.apply_runner_snapshot(rnbo.discover())
    ui.set_busy(False)

    # Optional startup actions
    ui.restore_from_saved_state()
    if ui.should_autoload_last_patch():
        ui.set_busy(True, "load")
        patch_name = ui.get_last_patch_name()
        if patch_name:
            rnbo.load_patch(patch_name)
            sleep(0.1)
            ui.apply_runner_snapshot(rnbo.discover())
        ui.set_busy(False)

    last_frame = 0.0
    last_refresh = 0.0
    last_activity = monotonic()

    is_dimmed = False
    is_sleeping = False

    def mark_activity() -> None:
        nonlocal last_activity, is_dimmed, is_sleeping
        last_activity = monotonic()

        if is_sleeping:
            display.wake()
            is_sleeping = False

        if is_dimmed:
            display.set_contrast(BRIGHTNESS_NORMAL)
            is_dimmed = False

    try:
        while True:
            now = monotonic()

            # Pull pending hardware events
            events = encoder.get_events()
            if events:
                mark_activity()

            for event in events:
                ui.handle_event(event)

            # Pull pending RNBO actions requested by UI
            for action in ui.pop_actions():
                if action.kind == "load_patch":
                    ui.set_busy(True, "load")
                    rnbo.load_patch(action.patch_name)
                    sleep(0.1)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "set_param":
                    rnbo.set_param(action.path, action.value)

                elif action.kind == "set_audio_device":
                    ui.set_busy(True, "audio")
                    rnbo.set_audio_device(action.device_name)
                    rnbo.restart_jack()
                    sleep(0.6)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "restart_jack":
                    ui.set_busy(True, "audio")
                    rnbo.restart_jack()
                    sleep(0.6)
                    ui.apply_runner_snapshot(rnbo.discover())
                    ui.set_busy(False)

                elif action.kind == "save_state":
                    ui.save_state()

            # Periodic discovery refresh
            if (now - last_refresh) >= REFRESH_SECONDS:
                last_refresh = now
                ui.set_busy(True, "refresh")
                ui.apply_runner_snapshot(rnbo.discover())
                ui.set_busy(False)

            # OLED dim / sleep policy
            idle = now - last_activity

            if (not is_sleeping) and idle >= SLEEP_TIMEOUT:
                display.sleep()
                is_sleeping = True

            elif (not is_dimmed) and idle >= DIM_TIMEOUT:
                display.set_contrast(BRIGHTNESS_DIM)
                is_dimmed = True

            # Draw at fixed-ish frame rate, but skip while sleeping
            if (not is_sleeping) and (now - last_frame) >= FRAME_DT:
                last_frame = now
                renderer.draw(ui.state)

            sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        encoder.close()
        display.wake()
        display.set_contrast(BRIGHTNESS_NORMAL)
        display.clear()
        display.show()


if __name__ == "__main__":
    main()
