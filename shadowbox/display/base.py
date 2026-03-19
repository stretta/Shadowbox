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

    def text(self, s: str, x: int, y: int) -> None:
        raise NotImplementedError

    def pixel(self, x: int, y: int, on: bool = True) -> None:
        raise NotImplementedError

    def hline(self, x: int, y: int, w: int, on: bool = True) -> None:
        raise NotImplementedError

    def vline(self, x: int, y: int, h: int, on: bool = True) -> None:
        raise NotImplementedError

    def rect(self, x: int, y: int, w: int, h: int, on: bool = True, fill: bool = False) -> None:
        raise NotImplementedError

    def set_contrast(self, value: int) -> None:
        pass

    def sleep(self) -> None:
        pass

    def wake(self) -> None:
        pass
