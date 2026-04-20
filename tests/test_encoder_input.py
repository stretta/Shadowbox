import importlib
import os
import sys
import types
import unittest
from unittest import mock


class _FakeCallback:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class _FakePigpioPi:
    def __init__(self) -> None:
        self.connected = True
        self.pin_values: dict[int, int] = {}
        self.glitch_filters: dict[int, int] = {}
        self.callbacks: list[_FakeCallback] = []
        self.stopped = False

    def set_mode(self, pin: int, mode: int) -> None:
        self.pin_values.setdefault(pin, 1)

    def set_pull_up_down(self, pin: int, pud: int) -> None:
        self.pin_values.setdefault(pin, 1)

    def set_glitch_filter(self, pin: int, glitch_us: int) -> None:
        self.glitch_filters[pin] = glitch_us

    def read(self, pin: int) -> int:
        return self.pin_values.get(pin, 1)

    def callback(self, pin: int, edge: int, func) -> _FakeCallback:
        callback = _FakeCallback()
        self.callbacks.append(callback)
        return callback

    def stop(self) -> None:
        self.stopped = True


class EncoderInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_pi = _FakePigpioPi()
        pigpio_module = types.ModuleType("pigpio")
        pigpio_module.INPUT = 0
        pigpio_module.PUD_UP = 1
        pigpio_module.EITHER_EDGE = 2
        pigpio_module.pi = lambda: self.fake_pi
        self._previous_pigpio = sys.modules.get("pigpio")
        sys.modules["pigpio"] = pigpio_module
        sys.modules.pop("shadowbox.encoder", None)
        self.encoder_module = importlib.import_module("shadowbox.encoder")

    def tearDown(self) -> None:
        sys.modules.pop("shadowbox.encoder", None)
        if self._previous_pigpio is None:
            sys.modules.pop("pigpio", None)
        else:
            sys.modules["pigpio"] = self._previous_pigpio

    def test_dedicated_back_button_emits_long_press_on_press(self) -> None:
        encoder = self.encoder_module.EncoderInput(back_pin=5)
        self.assertEqual(encoder.get_events(), [])

        self.fake_pi.pin_values[5] = 0
        events = encoder.get_events()
        self.assertEqual([event.kind for event in events], ["long_press"])

        self.assertEqual(encoder.get_events(), [])

        self.fake_pi.pin_values[5] = 1
        self.assertEqual(encoder.get_events(), [])

        self.fake_pi.pin_values[5] = 0
        events = encoder.get_events()
        self.assertEqual([event.kind for event in events], ["long_press"])
        self.assertEqual(self.fake_pi.glitch_filters[5], 0)

        encoder.close()
        self.assertTrue(all(callback.cancelled for callback in self.fake_pi.callbacks))
        self.assertTrue(self.fake_pi.stopped)

    def test_rotation_events_are_raw_detents_without_global_acceleration(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SHADOWBOX_ENCODER_ACCEL_FAST_SECONDS": "10",
                "SHADOWBOX_ENCODER_ACCEL_FAST_MULTIPLIER": "7",
                "SHADOWBOX_ENCODER_ACCEL_TURBO_SECONDS": "10",
                "SHADOWBOX_ENCODER_ACCEL_TURBO_MULTIPLIER": "9",
            },
            clear=False,
        ):
            encoder = self.encoder_module.EncoderInput()
        encoder._enc_accum = encoder.steps_per_detent - 1
        encoder._last_move_sign = 1
        self.fake_pi.pin_values[encoder.clk_pin] = 0
        self.fake_pi.pin_values[encoder.dt_pin] = 1

        encoder._on_ab(encoder.clk_pin, 0, 0)

        events = encoder.get_events()
        self.assertEqual([(event.kind, event.delta) for event in events], [("step", 1)])

    def test_waveshare_hat_maps_joystick_and_buttons_to_shadowbox_events(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SHADOWBOX_INPUT_KIND": "waveshare_144_hat",
            },
            clear=False,
        ):
            encoder = self.encoder_module.EncoderInput()

        self.fake_pi.pin_values[encoder.joy_up_pin] = 0
        events = encoder.get_events()
        self.assertEqual([(event.kind, event.delta) for event in events], [("step", -1)])

        self.fake_pi.pin_values[encoder.joy_up_pin] = 1
        self.assertEqual(encoder.get_events(), [])

        self.fake_pi.pin_values[encoder.key1_pin] = 0
        events = encoder.get_events()
        self.assertEqual([event.kind for event in events], ["long_press"])
        self.assertTrue(encoder.is_back_button_configured())
        self.assertTrue(encoder.is_back_button_pressed())

        self.fake_pi.pin_values[encoder.key1_pin] = 1
        self.assertEqual(encoder.get_events(), [])
        self.assertFalse(encoder.is_back_button_pressed())

        self.fake_pi.pin_values[encoder.key2_pin] = 0
        events = encoder.get_events()
        self.assertEqual([event.kind for event in events], ["short_press"])

        encoder.close()

    def test_st7735s_hat_display_defaults_to_waveshare_hat_input(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SHADOWBOX_DISPLAY": "st7735s_hat",
            },
            clear=False,
        ):
            encoder = self.encoder_module.EncoderInput()

        self.assertEqual(encoder.input_kind, "waveshare_144_hat")
        encoder.close()


if __name__ == "__main__":
    unittest.main()
