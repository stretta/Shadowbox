import struct
import unittest
from unittest import mock

from shadowbox.keypad import (
    EVIOCGRAB,
    EV_KEY,
    KEY_KPASTERISK,
    KEY_KPDOT,
    KEY_KPENTER,
    KEY_KPMINUS,
    KEY_KPPLUS,
    KEY_KPSLASH,
    KEY_BACKSPACE,
    NumericKeypadReader,
    keypad_event_for_key,
)


class NumericKeypadTests(unittest.TestCase):
    def test_numeric_keypad_mapping(self):
        self.assertEqual((keypad_event_for_key(79, 1).kind, keypad_event_for_key(79, 1).button_id), ("keypad_digit", "1"))
        self.assertEqual((keypad_event_for_key(82, 1).kind, keypad_event_for_key(82, 1).button_id), ("keypad_digit", "0"))
        self.assertEqual(keypad_event_for_key(KEY_KPPLUS, 1).kind, "keypad_space")
        self.assertEqual(keypad_event_for_key(KEY_KPDOT, 1).kind, "keypad_decimal")
        self.assertEqual(keypad_event_for_key(KEY_BACKSPACE, 1).kind, "keypad_backspace")
        self.assertEqual(keypad_event_for_key(KEY_KPENTER, 1).kind, "keypad_enter")
        self.assertEqual(keypad_event_for_key(KEY_KPMINUS, 1).kind, "keypad_sign")
        self.assertEqual(keypad_event_for_key(KEY_KPSLASH, 1).delta, -1)
        self.assertEqual(keypad_event_for_key(KEY_KPASTERISK, 1).delta, 1)
        self.assertIsNone(keypad_event_for_key(79, 0))
        self.assertIsNone(keypad_event_for_key(69, 1))

    def test_reader_grabs_device_and_decodes_keypress(self):
        event_struct = struct.Struct("@llHHi")
        data = event_struct.pack(0, 0, EV_KEY, 79, 1)
        with (
            mock.patch("shadowbox.keypad.os.open", return_value=12),
            mock.patch("shadowbox.keypad.os.close") as close,
            mock.patch("shadowbox.keypad.fcntl.ioctl") as ioctl,
            mock.patch("shadowbox.keypad.select.select", side_effect=[([12], [], []), ([], [], [])]),
            mock.patch("shadowbox.keypad.os.read", return_value=data),
        ):
            reader = NumericKeypadReader("/dev/input/by-id/test-event-kbd")

            events = reader.read_events()
            reader.close()

        self.assertEqual([(event.kind, event.button_id) for event in events], [("keypad_digit", "1")])
        ioctl.assert_any_call(12, EVIOCGRAB, 1)
        ioctl.assert_any_call(12, EVIOCGRAB, 0)
        close.assert_called_with(12)

    def test_reader_disconnects_cleanly_after_device_removal(self):
        with (
            mock.patch("shadowbox.keypad.os.open", return_value=12),
            mock.patch("shadowbox.keypad.os.close") as close,
            mock.patch("shadowbox.keypad.fcntl.ioctl"),
            mock.patch("shadowbox.keypad.select.select", return_value=([12], [], [])),
            mock.patch("shadowbox.keypad.os.read", side_effect=OSError("device removed")),
        ):
            reader = NumericKeypadReader("/dev/input/by-id/test-event-kbd")

            self.assertEqual(reader.read_events(), [])

        self.assertFalse(reader.is_connected)
        close.assert_called_with(12)


if __name__ == "__main__":
    unittest.main()
