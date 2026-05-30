#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shadowbox.touch import TouchZoneReader


def main() -> None:
    reader = TouchZoneReader(
        device=os.environ.get("SHADOWBOX_TOUCH_DEVICE") or None,
        width=int(os.environ.get("SHADOWBOX_TOUCH_WIDTH", "800"), 0),
        height=int(os.environ.get("SHADOWBOX_TOUCH_HEIGHT", "480"), 0),
    )
    print("Touch test running")
    print(f"device={reader.device}")
    print(f"x_range={reader.min_x}..{reader.max_x} y_range={reader.min_y}..{reader.max_y}")
    print("zones: top-left=BACK top-right=ENTER bottom-left=LEFT bottom-right=RIGHT")
    print("Tap the display. Ctrl+C to exit.\n")

    try:
        while True:
            for sample in reader.read_samples():
                print(
                    f"tap raw=({sample.x},{sample.y}) "
                    f"norm=({sample.normalized_x:.3f},{sample.normalized_y:.3f}) "
                    f"zone={sample.zone} action={sample.action}",
                    flush=True,
                )
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()


if __name__ == "__main__":
    main()
