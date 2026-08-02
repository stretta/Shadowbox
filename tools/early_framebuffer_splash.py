#!/usr/bin/env python3
"""Paint a minimal Shadowbox splash as soon as the final DSI framebuffer exists."""

from __future__ import annotations

import mmap
import os
from pathlib import Path
from time import monotonic, sleep

BACKGROUND = (15, 18, 18)
FOREGROUND = (244, 247, 242)
MUTED = (166, 176, 170)
ACCENT = (214, 255, 86)


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip(), 0)
    except (OSError, ValueError):
        return None


def framebuffer_geometry(framebuffer: Path, sysfs_root: Path = Path("/sys/class/graphics")) -> tuple[int, int, int, int] | None:
    sysfs = sysfs_root / framebuffer.name
    try:
        width_text, height_text = (sysfs / "virtual_size").read_text(encoding="ascii").strip().split(",", 1)
        width = int(width_text)
        height = int(height_text)
    except (OSError, ValueError):
        return None
    bits_per_pixel = _read_int(sysfs / "bits_per_pixel")
    if bits_per_pixel not in {16, 24, 32}:
        return None
    stride = _read_int(sysfs / "stride") or width * (bits_per_pixel // 8)
    return width, height, bits_per_pixel, stride


def framebuffer_driver(framebuffer: Path, sysfs_root: Path = Path("/sys/class/graphics")) -> str:
    try:
        return (sysfs_root / framebuffer.name / "name").read_text(encoding="ascii").strip()
    except OSError:
        return ""


def wait_for_framebuffer(
    framebuffer: Path,
    expected_width: int,
    expected_height: int,
    timeout: float,
    *,
    sysfs_root: Path = Path("/sys/class/graphics"),
    expected_driver: str = "",
) -> tuple[int, int, int, int] | None:
    deadline = monotonic() + max(0.0, timeout)
    while True:
        geometry = framebuffer_geometry(framebuffer, sysfs_root)
        driver = framebuffer_driver(framebuffer, sysfs_root)
        if (
            framebuffer.exists()
            and geometry is not None
            and geometry[:2] == (expected_width, expected_height)
            and (not expected_driver or driver == expected_driver)
        ):
            return geometry
        if monotonic() >= deadline:
            return None
        sleep(0.05)


def _font(repo_dir: Path, name: str, size: int):
    from PIL import ImageFont

    font_path = repo_dir / "assets" / "fonts" / name
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError:
        return ImageFont.load_default()


def render_splash(width: int, height: int, repo_dir: Path):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = _font(repo_dir, "IBMPlexSans-SemiBold.ttf", max(32, round(height * 0.13)))
    status_font = _font(repo_dir, "IBMPlexSans-Medium.ttf", max(18, round(height * 0.052)))
    hint_font = _font(repo_dir, "IBMPlexSans-Regular.ttf", max(16, round(height * 0.043)))

    title = "SHADOWBOX"
    status = "starting Shadowbox"
    hint = "please wait"
    title_box = draw.textbbox((0, 0), title, font=title_font)
    status_box = draw.textbbox((0, 0), status, font=status_font)
    hint_box = draw.textbbox((0, 0), hint, font=hint_font)
    title_h = title_box[3] - title_box[1]
    status_h = status_box[3] - status_box[1]
    hint_h = hint_box[3] - hint_box[1]
    status_gap = max(20, round(height * 0.075))
    hint_gap = max(12, round(height * 0.038))
    bar_gap = max(20, round(height * 0.06))
    bar_h = max(6, round(height * 0.016))
    block_h = title_h + status_gap + status_h + hint_gap + hint_h + bar_gap + bar_h
    y = max(12, (height - block_h) // 2)

    def centered_x(box: tuple[int, int, int, int]) -> int:
        return max(0, (width - (box[2] - box[0])) // 2)

    draw.text((centered_x(title_box), y - title_box[1]), title, font=title_font, fill=FOREGROUND)
    y += title_h + status_gap
    draw.text((centered_x(status_box), y - status_box[1]), status, font=status_font, fill=FOREGROUND)
    y += status_h + hint_gap
    draw.text((centered_x(hint_box), y - hint_box[1]), hint, font=hint_font, fill=MUTED)
    y += hint_h + bar_gap

    bar_w = max(80, round(width * 0.34))
    bar_x = (width - bar_w) // 2
    radius = max(2, bar_h // 2)
    draw.rounded_rectangle((bar_x, y, bar_x + bar_w, y + bar_h), radius=radius, outline=MUTED, width=1)
    segment_w = max(20, bar_w // 3)
    draw.rounded_rectangle(
        (bar_x + 1, y + 1, bar_x + segment_w, y + bar_h - 1),
        radius=max(1, radius - 1),
        fill=ACCENT,
    )
    return image


def pack_frame(image, bits_per_pixel: int, stride: int) -> bytes:
    width, height = image.size
    if bits_per_pixel == 32:
        packed = image.tobytes("raw", "BGRX")
    elif bits_per_pixel == 24:
        packed = image.tobytes("raw", "BGR")
    elif bits_per_pixel == 16:
        rgb = image.tobytes()
        data = bytearray(width * height * 2)
        for pixel in range(width * height):
            source = pixel * 3
            value = ((rgb[source] & 0xF8) << 8) | ((rgb[source + 1] & 0xFC) << 3) | (rgb[source + 2] >> 3)
            target = pixel * 2
            data[target] = value & 0xFF
            data[target + 1] = value >> 8
        packed = bytes(data)
    else:
        raise ValueError(f"Unsupported framebuffer depth: {bits_per_pixel}")

    row_bytes = width * (bits_per_pixel // 8)
    if stride == row_bytes:
        return packed
    frame = bytearray(stride * height)
    for row in range(height):
        source = row * row_bytes
        target = row * stride
        frame[target : target + row_bytes] = packed[source : source + row_bytes]
    return bytes(frame)


def main() -> int:
    if os.environ.get("SHADOWBOX_DISPLAY", "").strip().lower() != "waveshare_5inch_dsi":
        return 0
    started = monotonic()
    repo_dir = Path(__file__).resolve().parent.parent
    framebuffer = Path(os.environ.get("SHADOWBOX_DSI_FRAMEBUFFER", "/dev/fb0"))
    width = int(os.environ.get("SHADOWBOX_DSI_WIDTH", "800"), 0)
    height = int(os.environ.get("SHADOWBOX_DSI_HEIGHT", "480"), 0)
    timeout = float(os.environ.get("SHADOWBOX_EARLY_SPLASH_TIMEOUT", "14"))
    expected_driver = os.environ.get("SHADOWBOX_EARLY_SPLASH_FRAMEBUFFER_NAME", "vc4drmfb").strip()
    # Prepare the logical image while KMS is loading. Do not inspect or open
    # fb0 until the final driver replaces Raspberry Pi's temporary simplefb.
    image = render_splash(width, height, repo_dir)
    geometry = wait_for_framebuffer(
        framebuffer,
        width,
        height,
        timeout,
        expected_driver=expected_driver,
    )
    if geometry is None:
        driver_hint = f" using {expected_driver}" if expected_driver else ""
        print(f"Early splash skipped: {framebuffer} did not reach {width}x{height}{driver_hint} within {timeout:g}s")
        return 0
    _, _, bits_per_pixel, stride = geometry
    frame = pack_frame(image, bits_per_pixel, stride)
    # The fb0 path can be rebound while userspace is rendering/packing. Refuse
    # to write if its final geometry or driver changed underneath us.
    if framebuffer_geometry(framebuffer) != geometry or (
        expected_driver and framebuffer_driver(framebuffer) != expected_driver
    ):
        print("Early splash skipped: framebuffer changed while the frame was being prepared")
        return 0
    frame_size = stride * height
    try:
        descriptor = os.open(framebuffer, os.O_RDWR)
        try:
            with mmap.mmap(descriptor, frame_size, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ) as mapped:
                mapped[:frame_size] = frame
                mapped.flush()
        finally:
            os.close(descriptor)
    except OSError as exc:
        print(f"Early splash skipped: could not write {framebuffer}: {exc}")
        return 0
    driver = framebuffer_driver(framebuffer)
    print(
        f"Early splash displayed after {monotonic() - started:.3f}s on {framebuffer} "
        f"({width}x{height}x{bits_per_pixel}, {driver or 'unknown driver'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
