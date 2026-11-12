"""Цифрові фільтри низьких і високих частот (чиста обробка кадрів, без Qt).

Вікно фільтра n×n, 3 ≤ n ≤ 30.

* ФНЧ — усереднення (ядро з одиниць, CF = n²) або гаусове ядро.
* ФВЧ = оригінал − ФНЧ(n): сума коефіцієнтів дорівнює 0, постійна складова
  не пропускається. Для усереднення при n = 3 це ядро з лекцій
  (1/9)·[[-1,-1,-1],[-1,8,-1],[-1,-1,-1]].

Фільтри OpenCV обробляють канали незалежно, тому один код підходить і для
кольорового, і для монохромного відео.
"""

import functools

import cv2
import numpy as np

from .state import (
    ColorMode,
    FilterMode,
    HighpassView,
    KernelKind,
    Params,
    clamp_gain,
    clamp_window,
)


@functools.cache
def _gauss_kernel(n: int) -> np.ndarray:
    # σ ≤ 0 → OpenCV підбирає σ за розміром ядра; на відміну від cv2.GaussianBlur
    # працює й для парних n.
    return cv2.getGaussianKernel(n, -1, cv2.CV_32F)


def lowpass(img: np.ndarray, n: int, kernel: KernelKind = KernelKind.BOX) -> np.ndarray:
    """ФНЧ з вікном n×n."""
    n = clamp_window(n)
    if kernel is KernelKind.BOX:
        return cv2.blur(img, (n, n))
    k = _gauss_kernel(n)
    return cv2.sepFilter2D(img, -1, k, k)


def highpass(
    img: np.ndarray,
    n: int,
    kernel: KernelKind = KernelKind.BOX,
    view: HighpassView = HighpassView.ABS,
    gain: int = 4,
) -> np.ndarray:
    """ФВЧ = оригінал − ФНЧ(n).

    ``ABS``    — модуль різниці (світлі контури на чорному);
    ``OFFSET`` — різниця зі зсувом 128 (сірий рельєф).
    """
    g = float(clamp_gain(gain))
    low = lowpass(img, n, kernel)
    if view is HighpassView.ABS:
        return cv2.convertScaleAbs(cv2.absdiff(img, low), alpha=g)
    return cv2.addWeighted(img, g, low, -g, 128.0)


def _to_bgr(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def process_pair(frame_bgr: np.ndarray, p: Params) -> tuple[np.ndarray, np.ndarray]:
    """Повертає (оригінал, результат) у BGR.

    Оригінал — це завжди необроблений кадр камери (кольоровий), навіть якщо для
    результату обрано монохромний режим.
    """
    src = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if p.color is ColorMode.MONO else frame_bgr
    if p.filter is FilterMode.NONE:
        out = src
    elif p.filter is FilterMode.LOWPASS:
        out = lowpass(src, p.size, p.kernel)
    else:
        out = highpass(src, p.size, p.kernel, p.hp_view, p.gain)
    return frame_bgr, _to_bgr(out)


def process(frame_bgr: np.ndarray, p: Params) -> np.ndarray:
    """Результат обробки кадра (BGR, 3 канали)."""
    return process_pair(frame_bgr, p)[1]
