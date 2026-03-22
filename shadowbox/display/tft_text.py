from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import warnings

from PIL import Image, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONT_CANDIDATES = {
    "thin": [
        _FONT_DIR / "IBMPlexSans-Light.ttf",
        _FONT_DIR / "IBMPlexSans-Regular.ttf",
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Light.ttf"),
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Regular.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-Light.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "regular": [
        _FONT_DIR / "IBMPlexSans-Regular.ttf",
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Regular.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "medium": [
        _FONT_DIR / "IBMPlexSans-Medium.ttf",
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Medium.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-Medium.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "semibold": [
        _FONT_DIR / "IBMPlexSans-SemiBold.ttf",
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-SemiBold.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-SemiBold.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "bold": [
        _FONT_DIR / "IBMPlexSans-Bold.ttf",
        _FONT_DIR / "IBMPlexSans-SemiBold.ttf",
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-SemiBold.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-Bold.ttf"),
        Path("/usr/share/fonts/IBM-Plex-Sans/IBMPlexSans-SemiBold.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
}
_MEASURE_DRAW = ImageDraw.Draw(Image.new("L", (1, 1), 0))
_WARNED_FALLBACKS: set[str] = set()


def font_size_for_scale(scale: int) -> int:
    scale = max(1, int(scale))
    size_map = {
        1: 12,
        2: 18,
        3: 26,
        4: 34,
    }
    return size_map.get(scale, 12 + ((scale - 1) * 8))


@lru_cache(maxsize=None)
def load_font(weight: str, scale: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = font_size_for_scale(scale)
    candidates = _FONT_CANDIDATES.get(weight, _FONT_CANDIDATES["regular"])
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    if weight not in _WARNED_FALLBACKS:
        warnings.warn(
            f"Shadowbox could not load IBM Plex Sans for '{weight}'. Falling back to Pillow default font.",
            RuntimeWarning,
            stacklevel=2,
        )
        _WARNED_FALLBACKS.add(weight)
    return ImageFont.load_default()


def measure_text(text: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
    font = load_font(weight, scale)
    bbox = _MEASURE_DRAW.textbbox((0, 0), str(text), font=font)
    return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])


def line_height(scale: int = 1, weight: str = "regular") -> int:
    font = load_font(weight, scale)
    bbox = _MEASURE_DRAW.textbbox((0, 0), "Ag", font=font)
    return max(1, bbox[3] - bbox[1] + 3)


def render_text_mask(text: str, scale: int = 1, weight: str = "regular") -> Image.Image:
    text = str(text)
    font = load_font(weight, scale)
    bbox = _MEASURE_DRAW.textbbox((0, 0), text, font=font)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    draw.text((-bbox[0], -bbox[1]), text, font=font, fill=255)
    return image


def mask_to_rgb(mask: Image.Image, fg_color: tuple[int, int, int], bg_color: tuple[int, int, int]) -> Image.Image:
    canvas = Image.new("RGB", mask.size, bg_color)
    canvas.paste(Image.new("RGB", mask.size, fg_color), (0, 0), mask)
    return canvas
