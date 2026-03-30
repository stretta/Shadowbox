from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import warnings

from PIL import Image, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def _font_file_candidates(*names: str) -> list[Path | str]:
    candidates: list[Path | str] = []
    for name in names:
        candidates.append(_FONT_DIR / name)
        candidates.append(Path("/usr/share/fonts/truetype/ibm-plex") / name)
        candidates.append(Path("/usr/share/fonts/IBM-Plex-Sans") / name)
    return candidates


_FONT_CANDIDATES = {
    "thin": [
        *_font_file_candidates("IBMPlexSans-Light.ttf", "IBMPlexSans-Regular.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-Light.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "thin-italic": [
        *_font_file_candidates("IBMPlexSans-LightItalic.ttf", "IBMPlexSans-Italic.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-LightItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans.ttf",
    ],
    "regular": [
        *_font_file_candidates("IBMPlexSans-Regular.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "italic": [
        *_font_file_candidates("IBMPlexSans-Italic.ttf", "IBMPlexSans-Regular.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-Italic.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans.ttf",
    ],
    "medium": [
        *_font_file_candidates("IBMPlexSans-Medium.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-Medium.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "medium-italic": [
        *_font_file_candidates("IBMPlexSans-MediumItalic.ttf", "IBMPlexSans-Italic.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-MediumItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "semibold": [
        *_font_file_candidates("IBMPlexSans-SemiBold.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-SemiBold.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "semibold-italic": [
        *_font_file_candidates("IBMPlexSans-SemiBoldItalic.ttf", "IBMPlexSans-BoldItalic.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-SemiBoldItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "bold": [
        *_font_file_candidates("IBMPlexSans-Bold.ttf", "IBMPlexSans-SemiBold.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-Bold.ttf", "IBMPlexSansCondensed-SemiBold.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "bold-italic": [
        *_font_file_candidates("IBMPlexSans-BoldItalic.ttf", "IBMPlexSans-SemiBoldItalic.ttf"),
        *_font_file_candidates("IBMPlexSansCondensed-BoldItalic.ttf", "IBMPlexSansCondensed-SemiBoldItalic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-thin": [
        *_font_file_candidates("IBMPlexSansCondensed-Light.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        *_font_file_candidates("IBMPlexSans-Light.ttf", "IBMPlexSans-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "condensed-thin-italic": [
        *_font_file_candidates("IBMPlexSansCondensed-LightItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        *_font_file_candidates("IBMPlexSans-LightItalic.ttf", "IBMPlexSans-Italic.ttf"),
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-regular": [
        *_font_file_candidates("IBMPlexSansCondensed-Regular.ttf"),
        *_font_file_candidates("IBMPlexSans-Regular.ttf"),
        "DejaVuSans.ttf",
    ],
    "condensed-italic": [
        *_font_file_candidates("IBMPlexSansCondensed-Italic.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        *_font_file_candidates("IBMPlexSans-Italic.ttf", "IBMPlexSans-Regular.ttf"),
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-medium": [
        *_font_file_candidates("IBMPlexSansCondensed-Medium.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        *_font_file_candidates("IBMPlexSans-Medium.ttf", "IBMPlexSans-Regular.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-medium-italic": [
        *_font_file_candidates("IBMPlexSansCondensed-MediumItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        *_font_file_candidates("IBMPlexSans-MediumItalic.ttf", "IBMPlexSans-Italic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-semibold": [
        *_font_file_candidates("IBMPlexSansCondensed-SemiBold.ttf", "IBMPlexSansCondensed-Regular.ttf"),
        *_font_file_candidates("IBMPlexSans-SemiBold.ttf", "IBMPlexSans-Regular.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-semibold-italic": [
        *_font_file_candidates("IBMPlexSansCondensed-SemiBoldItalic.ttf", "IBMPlexSansCondensed-Italic.ttf"),
        *_font_file_candidates("IBMPlexSans-SemiBoldItalic.ttf", "IBMPlexSans-Italic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-bold": [
        *_font_file_candidates("IBMPlexSansCondensed-Bold.ttf", "IBMPlexSansCondensed-SemiBold.ttf"),
        *_font_file_candidates("IBMPlexSans-Bold.ttf", "IBMPlexSans-SemiBold.ttf"),
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
    "condensed-bold-italic": [
        *_font_file_candidates("IBMPlexSansCondensed-BoldItalic.ttf", "IBMPlexSansCondensed-SemiBoldItalic.ttf"),
        *_font_file_candidates("IBMPlexSans-BoldItalic.ttf", "IBMPlexSans-SemiBoldItalic.ttf"),
        "DejaVuSans-BoldOblique.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ],
}
_MEASURE_DRAW = ImageDraw.Draw(Image.new("L", (1, 1), 0))
_WARNED_FALLBACKS: set[str] = set()
_FONT_ALIASES = {
    "light": "thin",
    "light-italic": "thin-italic",
    "condensed": "condensed-regular",
    "condensed-light": "condensed-thin",
    "condensed-light-italic": "condensed-thin-italic",
    "condensed-lightitalic": "condensed-thin-italic",
    "condensed-mediumitalic": "condensed-medium-italic",
    "condensed-semibolditalic": "condensed-semibold-italic",
    "condensed-bolditalic": "condensed-bold-italic",
    "regular-condensed": "condensed-regular",
    "italic-condensed": "condensed-italic",
    "medium-condensed": "condensed-medium",
    "mediumitalic-condensed": "condensed-medium-italic",
    "semibold-condensed": "condensed-semibold",
    "semibolditalic-condensed": "condensed-semibold-italic",
    "bold-condensed": "condensed-bold",
    "bolditalic-condensed": "condensed-bold-italic",
    "regular-italic": "italic",
    "oblique": "italic",
    "mediumitalic": "medium-italic",
    "semibolditalic": "semibold-italic",
    "bolditalic": "bold-italic",
}


def font_size_for_scale(scale: int) -> int:
    scale = max(1, int(scale))
    size_map = {
        1: 12,
        2: 18,
        3: 26,
        4: 34,
    }
    return size_map.get(scale, 12 + ((scale - 1) * 8))


def _normalize_weight_name(weight: str) -> str:
    normalized = weight.strip().lower().replace("_", "-").replace(" ", "-")
    return _FONT_ALIASES.get(normalized, normalized)


@lru_cache(maxsize=None)
def load_font(weight: str, scale: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = font_size_for_scale(scale)
    normalized_weight = _normalize_weight_name(weight)
    candidates = _FONT_CANDIDATES.get(normalized_weight, _FONT_CANDIDATES["regular"])
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    if normalized_weight not in _WARNED_FALLBACKS:
        warnings.warn(
            f"Shadowbox could not load IBM Plex Sans for '{normalized_weight}'. Falling back to Pillow default font.",
            RuntimeWarning,
            stacklevel=2,
        )
        _WARNED_FALLBACKS.add(normalized_weight)
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
