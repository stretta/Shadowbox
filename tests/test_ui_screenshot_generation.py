import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "tools" / "generate_ui_screenshots.py"


class UIScreenshotGenerationTests(unittest.TestCase):
    def test_generates_every_custom_editor_as_an_800_by_480_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            subprocess.run(
                [sys.executable, str(MODULE_PATH), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            expected = {entry["file"] for entry in manifest["screenshots"]}
            pngs = sorted(output.glob("*.png"))

            self.assertEqual({path.name for path in pngs}, expected)
            for path in pngs:
                data = path.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
                self.assertEqual((width, height), (800, 480))
                self.assertEqual(bit_depth, 8)
                self.assertEqual(color_type, 2)


if __name__ == "__main__":
    unittest.main()
