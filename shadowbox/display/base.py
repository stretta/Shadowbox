from __future__ import annotations


class DisplayBackend:
    width: int
    height: int

    def init(self) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def show(self) -> None:
        raise NotImplementedError

    def text(self, s: str, x: int, y: int, on: bool = True) -> None:
        raise NotImplementedError

    def text_scaled(self, s: str, x: int, y: int, scale: int = 1, on: bool = True) -> None:
        raise NotImplementedError

    def text_with_style(self, s: str, x: int, y: int, scale: int = 1, weight: str = "regular", on: bool = True) -> None:
        self.text_scaled(s, x, y, scale, on=on)

    def measure_text(self, s: str, scale: int = 1, weight: str = "regular") -> tuple[int, int]:
        scale = max(1, int(scale))
        return len(str(s)) * 6 * scale, 7 * scale

    def line_height(self, scale: int = 1, weight: str = "regular") -> int:
        scale = max(1, int(scale))
        return 8 * scale

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        raise NotImplementedError

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        raise NotImplementedError

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        raise NotImplementedError

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        raise NotImplementedError

    def fill_rect_level(self, x: int, y: int, w: int, h: int, level: int) -> None:
        self.rect(x, y, w, h, on=level >= 128, fill=True)

    def set_contrast(self, value: int) -> None:
        pass

    def sleep(self) -> None:
        pass

    def wake(self) -> None:
        pass
