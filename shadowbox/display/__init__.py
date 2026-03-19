from shadowbox.display.ssd1306 import SSD1306Display
from shadowbox.display.ssd1309 import SSD1309Display


def create_display(kind: str = "ssd1306", **kwargs):
    if kind == "ssd1306":
        return SSD1306Display(**kwargs)
    if kind == "ssd1309":
        return SSD1309Display(**kwargs)
    raise ValueError(f"Unknown display backend: {kind}")


__all__ = ["SSD1306Display", "SSD1309Display", "create_display"]
