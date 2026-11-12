"""Стан програми: режими та параметри обробки (без залежності від Qt)."""

from dataclasses import dataclass, replace
from enum import Enum

WIN_MIN = 3
WIN_MAX = 30
GAIN_MIN = 1
GAIN_MAX = 10


class ColorMode(Enum):
    COLOR = "color"
    MONO = "mono"


class FilterMode(Enum):
    NONE = "none"
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"


class KernelKind(Enum):
    BOX = "box"
    GAUSS = "gauss"


class HighpassView(Enum):
    ABS = "abs"
    OFFSET = "offset"


def clamp_window(n: int) -> int:
    """Обмежити розмір вікна фільтра діапазоном [WIN_MIN, WIN_MAX]."""
    return max(WIN_MIN, min(WIN_MAX, int(n)))


def clamp_gain(g: int) -> int:
    return max(GAIN_MIN, min(GAIN_MAX, int(g)))


@dataclass(frozen=True, slots=True)
class Params:
    """Незмінні параметри обробки; GUI підміняє об'єкт цілком, потік лише читає."""

    color: ColorMode = ColorMode.COLOR
    filter: FilterMode = FilterMode.LOWPASS
    kernel: KernelKind = KernelKind.BOX
    size: int = 7
    hp_view: HighpassView = HighpassView.ABS
    gain: int = 4
    compare: bool = False

    def with_(self, **changes) -> "Params":
        if "size" in changes:
            changes["size"] = clamp_window(changes["size"])
        if "gain" in changes:
            changes["gain"] = clamp_gain(changes["gain"])
        return replace(self, **changes)
