import importlib
import os
import sys
import types
import unittest
from unittest import mock

from shadowbox.touch import TouchAction, TouchLayout, direct_action_for_point, zone_for_point


class TouchZoneMappingTests(unittest.TestCase):
    def test_quadrants_map_to_existing_shadowbox_actions(self) -> None:
        self.assertEqual(zone_for_point(0.25, 0.25), ("back", "long_press"))
        self.assertEqual(zone_for_point(0.75, 0.25), ("enter", "short_press"))
        self.assertEqual(zone_for_point(0.25, 0.75), ("left", "step:-1"))
        self.assertEqual(zone_for_point(0.75, 0.75), ("right", "step:+1"))


class TouchDirectMappingTests(unittest.TestCase):
    def test_direct_touch_regions_emit_semantic_actions(self) -> None:
        self.assertEqual(direct_action_for_point(0.05, 0.05), TouchAction("tap_back"))
        self.assertEqual(direct_action_for_point(0.95, 0.25), TouchAction("page_up"))
        self.assertEqual(direct_action_for_point(0.95, 0.75), TouchAction("page_down"))
        self.assertEqual(direct_action_for_point(0.50, 0.20), TouchAction("tap_row", index=0))
        self.assertEqual(direct_action_for_point(0.50, 0.85), TouchAction("tap_row", index=5))
        self.assertEqual(direct_action_for_point(0.80, 0.95), TouchAction("tap_button", button_id="primary"))

    def test_direct_touch_slider_target_emits_normalized_value(self) -> None:
        layout = TouchLayout(800, 480)
        layout.add_target("edit_slider", 100, 200, 600, 80, action_kind="set_edit_value", button_id="value_slider")

        self.assertEqual(
            direct_action_for_point(400 / 799, 240 / 479, layout=layout),
            TouchAction("set_edit_value", button_id="value_slider", value=300 / 599),
        )

    def test_direct_touch_step16_target_emits_step_action(self) -> None:
        layout = TouchLayout(800, 480)
        layout.add_target("step16_cell", 100, 120, 80, 96, action_kind="tap_step16", index=7)

        self.assertEqual(
            direct_action_for_point((100 + 40) / 799, (120 + 48) / 479, layout=layout),
            TouchAction("tap_step16", index=7),
        )


class _FakeTouchReader:
    def __init__(self, *, device=None, width=800, height=480) -> None:
        self.device = device
        self.width = width
        self.height = height
        self.pressed = False
        self.closed = False
        self.samples = []

    def read_samples(self):
        samples = self.samples[:]
        self.samples.clear()
        return samples

    def close(self) -> None:
        self.closed = True


class EncoderTouchZoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_pigpio = sys.modules.get("pigpio")
        pigpio_module = types.ModuleType("pigpio")
        pigpio_module.INPUT = 0
        pigpio_module.PUD_UP = 1
        pigpio_module.EITHER_EDGE = 2
        pigpio_module.pi = lambda: None
        sys.modules["pigpio"] = pigpio_module
        sys.modules.pop("shadowbox.encoder", None)
        self.encoder_module = importlib.import_module("shadowbox.encoder")

    def tearDown(self) -> None:
        sys.modules.pop("shadowbox.encoder", None)
        if self._previous_pigpio is None:
            sys.modules.pop("pigpio", None)
        else:
            sys.modules["pigpio"] = self._previous_pigpio

    def test_touch_zone_reader_events_are_encoder_events(self) -> None:
        sample_type = types.SimpleNamespace
        with (
            mock.patch.dict(os.environ, {"SHADOWBOX_INPUT_KIND": "touch_zones"}, clear=False),
            mock.patch.object(self.encoder_module, "TouchZoneReader", _FakeTouchReader),
        ):
            encoder = self.encoder_module.EncoderInput()

        encoder._touch_reader.samples.extend(
            [
                sample_type(action="step:-1"),
                sample_type(action="step:+1"),
                sample_type(action="short_press"),
                sample_type(action="long_press"),
            ]
        )

        events = encoder.get_events()
        self.assertEqual(
            [(event.kind, event.delta) for event in events],
            [("step", -1), ("step", 1), ("short_press", 0), ("long_press", 0)],
        )
        self.assertTrue(encoder.is_back_button_configured())
        encoder.close()
        self.assertTrue(encoder._touch_reader.closed)

    def test_waveshare_5inch_dsi_defaults_to_touch_direct(self) -> None:
        with (
            mock.patch.dict(os.environ, {"SHADOWBOX_DISPLAY": "waveshare_5inch_dsi"}, clear=False),
            mock.patch.object(self.encoder_module, "TouchZoneReader", _FakeTouchReader),
        ):
            encoder = self.encoder_module.EncoderInput()

        self.assertEqual(encoder.input_kind, "touch_direct")

    def test_touch_direct_reader_events_are_semantic_events(self) -> None:
        sample_type = types.SimpleNamespace
        with (
            mock.patch.dict(os.environ, {"SHADOWBOX_INPUT_KIND": "touch_direct"}, clear=False),
            mock.patch.object(self.encoder_module, "TouchZoneReader", _FakeTouchReader),
        ):
            encoder = self.encoder_module.EncoderInput()

        encoder._touch_reader.samples.extend(
            [
                sample_type(normalized_x=0.5, normalized_y=0.2, pressed=False),
                sample_type(normalized_x=0.05, normalized_y=0.05, pressed=False),
                sample_type(normalized_x=0.95, normalized_y=0.75, pressed=False),
                sample_type(normalized_x=0.8, normalized_y=0.95, pressed=False),
            ]
        )

        events = encoder.get_events()
        self.assertEqual(
            [(event.kind, event.index, event.button_id) for event in events],
            [
                ("tap_row", 0, ""),
                ("tap_back", None, ""),
                ("page_down", None, ""),
                ("tap_button", None, "primary"),
            ],
        )
        self.assertTrue(encoder.is_back_button_configured())
        encoder.close()
        self.assertTrue(encoder._touch_reader.closed)

    def test_touch_direct_ignores_pressed_rows_but_streams_slider_values(self) -> None:
        sample_type = types.SimpleNamespace
        with (
            mock.patch.dict(os.environ, {"SHADOWBOX_INPUT_KIND": "touch_direct"}, clear=False),
            mock.patch.object(self.encoder_module, "TouchZoneReader", _FakeTouchReader),
        ):
            encoder = self.encoder_module.EncoderInput()

        layout = TouchLayout(800, 480)
        layout.add_target("row", 0, 80, 700, 80, action_kind="tap_row", index=1)
        layout.add_target("edit_slider", 100, 220, 600, 80, action_kind="set_edit_value", button_id="value_slider")
        encoder.set_touch_layout(layout)
        encoder._touch_reader.samples.extend(
            [
                sample_type(normalized_x=0.5, normalized_y=100 / 479, pressed=True),
                sample_type(normalized_x=400 / 799, normalized_y=240 / 479, pressed=True),
                sample_type(normalized_x=0.5, normalized_y=100 / 479, pressed=False),
            ]
        )

        events = encoder.get_events()
        self.assertEqual(
            [(event.kind, event.index, event.button_id, event.value) for event in events],
            [
                ("set_edit_value", None, "value_slider", 300 / 599),
                ("tap_row", 1, "", None),
            ],
        )


if __name__ == "__main__":
    unittest.main()
