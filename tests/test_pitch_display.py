import unittest
import sys
import types

from shadowbox.editors.pitch_display import normalize_pitch_to_midi_note


pythonosc_module = types.ModuleType("pythonosc")
udp_client_module = types.ModuleType("pythonosc.udp_client")
udp_client_module.SimpleUDPClient = object
pythonosc_module.udp_client = udp_client_module
sys.modules.setdefault("pythonosc", pythonosc_module)
sys.modules.setdefault("pythonosc.udp_client", udp_client_module)

from shadowbox.renderer import ShadowboxRenderer


class _StubDisplay:
    width = 128
    height = 32


class PitchDisplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = ShadowboxRenderer(_StubDisplay())

    def test_normalize_pitch_to_midi_note_accepts_numeric_inputs(self) -> None:
        self.assertEqual(normalize_pitch_to_midi_note(69), 69)
        self.assertEqual(normalize_pitch_to_midi_note(69.49), 69)
        self.assertEqual(normalize_pitch_to_midi_note("69.5"), 70)
        self.assertEqual(normalize_pitch_to_midi_note(" 60 "), 60)
        self.assertEqual(normalize_pitch_to_midi_note([57.6]), 58)

    def test_normalize_pitch_to_midi_note_rejects_non_numeric_inputs(self) -> None:
        self.assertIsNone(normalize_pitch_to_midi_note(None))
        self.assertIsNone(normalize_pitch_to_midi_note("-"))
        self.assertIsNone(normalize_pitch_to_midi_note("A4"))
        self.assertIsNone(normalize_pitch_to_midi_note(float("nan")))
        self.assertIsNone(normalize_pitch_to_midi_note(True))

    def test_pitch_display_segments_use_midi_integer_for_numeric_pitch(self) -> None:
        segments = self.renderer._pitch_display_segments("69.8", 2)
        self.assertEqual(
            segments,
            [("70", 2, "regular"), (" ", 2, "regular"), ("A#4", 2, "medium")],
        )

    def test_pitch_display_segments_only_fall_back_for_non_numeric_pitch(self) -> None:
        segments = self.renderer._pitch_display_segments("A4", 2)
        self.assertEqual(segments, [("A4", 2, "medium")])


if __name__ == "__main__":
    unittest.main()
