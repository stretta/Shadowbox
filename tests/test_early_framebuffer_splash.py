import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parent.parent / "tools" / "early_framebuffer_splash.py"
SPEC = importlib.util.spec_from_file_location("early_framebuffer_splash", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EarlyFramebufferSplashTests(unittest.TestCase):
    def test_reads_geometry_and_stride_from_sysfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            framebuffer = root / "dev" / "fb0"
            framebuffer.parent.mkdir()
            framebuffer.touch()
            sysfs = root / "sys" / "fb0"
            sysfs.mkdir(parents=True)
            (sysfs / "virtual_size").write_text("800,480\n", encoding="ascii")
            (sysfs / "bits_per_pixel").write_text("32\n", encoding="ascii")
            (sysfs / "stride").write_text("3328\n", encoding="ascii")
            (sysfs / "name").write_text("vc4drmfb\n", encoding="ascii")

            self.assertEqual(MODULE.framebuffer_geometry(framebuffer, root / "sys"), (800, 480, 32, 3328))
            self.assertEqual(MODULE.framebuffer_driver(framebuffer, root / "sys"), "vc4drmfb")
            self.assertEqual(
                MODULE.wait_for_framebuffer(
                    framebuffer,
                    800,
                    480,
                    0,
                    sysfs_root=root / "sys",
                    expected_driver="vc4drmfb",
                ),
                (800, 480, 32, 3328),
            )
            self.assertIsNone(
                MODULE.wait_for_framebuffer(
                    framebuffer,
                    800,
                    480,
                    0,
                    sysfs_root=root / "sys",
                    expected_driver="simple",
                )
            )
            self.assertIsNone(MODULE.wait_for_framebuffer(framebuffer, 640, 480, 0, sysfs_root=root / "sys"))

    def test_packs_bgrx_rows_with_framebuffer_padding(self) -> None:
        class FakeImage:
            size = (2, 1)

            def tobytes(self, *args):
                if args == ("raw", "BGRX"):
                    return bytes((3, 2, 1, 0, 6, 5, 4, 0))
                raise AssertionError(args)

        self.assertEqual(
            MODULE.pack_frame(FakeImage(), 32, 12),
            bytes((3, 2, 1, 0, 6, 5, 4, 0, 0, 0, 0, 0)),
        )

    def test_renders_requested_dimensions(self) -> None:
        try:
            import PIL
        except ImportError:
            self.skipTest("Pillow is not installed in this development environment")
        if not getattr(PIL, "__file__", None):
            self.skipTest("another display test installed a lightweight Pillow stub")
        repo_dir = Path(__file__).resolve().parent.parent
        image = MODULE.render_splash(800, 480, repo_dir)
        self.assertEqual(image.size, (800, 480))
        self.assertNotEqual(image.getpixel((400, 240)), MODULE.BACKGROUND)


if __name__ == "__main__":
    unittest.main()
