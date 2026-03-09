"""
Shadowbox
Hardware UI for RNBO Runner

https://github.com/stretta/shadowbox
"""

#!/usr/bin/env python3

from time import monotonic, sleep

from display import SSD1306Display
from encoder import EncoderInput
from rnbo import RNBOClient
from ui import ShadowboxUI
from renderer import ShadowboxRenderer


FPS = 20
FRAME_DT = 1.0 / FPS
REFRESH_SECONDS = 3.0


def main():
    display = SSD1306Display()
    display.init()

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

    try:
        while True:
            now = monotonic()

            # Pull pending hardware events
            for event in encoder.get_events():
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

            # Draw at fixed-ish frame rate
            if (now - last_frame) >= FRAME_DT:
                last_frame = now
                renderer.draw(ui.state)

            sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        encoder.close()
        display.clear()
        display.show()


if __name__ == "__main__":
    main()
