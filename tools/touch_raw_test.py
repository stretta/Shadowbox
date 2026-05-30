#!/usr/bin/env python3

from __future__ import annotations

import os
import select
import struct
import sys
import time


EVENT_STRUCT = struct.Struct("=llHHi")
NAMES = {
    (0, 0): "SYN_REPORT",
    (1, 330): "BTN_TOUCH",
    (3, 0): "ABS_X",
    (3, 1): "ABS_Y",
    (3, 47): "ABS_MT_SLOT",
    (3, 53): "ABS_MT_X",
    (3, 54): "ABS_MT_Y",
    (3, 57): "ABS_MT_TRACKING_ID",
}


def main() -> None:
    device = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHADOWBOX_TOUCH_DEVICE", "/dev/input/event0")
    seconds = float(os.environ.get("SHADOWBOX_TOUCH_RAW_SECONDS", "45"))
    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    print(f"Raw touch event dump for {device}; touch the screen now.")
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            readable, _writable, _errors = select.select([fd], [], [], 0.5)
            if not readable:
                continue
            data = os.read(fd, EVENT_STRUCT.size * 32)
            for offset in range(0, len(data) - (EVENT_STRUCT.size - 1), EVENT_STRUCT.size):
                _sec, _usec, event_type, code, value = EVENT_STRUCT.unpack_from(data, offset)
                print(f"type={event_type} code={code} value={value} name={NAMES.get((event_type, code), '')}", flush=True)
    finally:
        os.close(fd)
    print("Raw dump done.")


if __name__ == "__main__":
    main()
