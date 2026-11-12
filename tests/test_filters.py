import cv2
import numpy as np
import pytest

from cv.video_filters.filters import highpass, lowpass, process, process_pair
from cv.video_filters.state import (
    WIN_MAX,
    WIN_MIN,
    ColorMode,
    FilterMode,
    HighpassView,
    KernelKind,
    Params,
    clamp_window,
)

SIZES = range(WIN_MIN, WIN_MAX + 1)


def noisy(shape=(48, 64, 3), seed=0, sigma=40.0, mean=128.0):
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(mean, sigma, shape), 0, 255).astype(np.uint8)


def test_clamp_window():
    assert clamp_window(2) == 3
    assert clamp_window(3) == 3
    assert clamp_window(30) == 30
    assert clamp_window(31) == 30
    assert clamp_window(-5) == 3


def test_params_clamps_size_and_gain():
    p = Params().with_(size=100, gain=0)
    assert p.size == WIN_MAX
    assert p.gain == 1
    assert Params().with_(size=1).size == WIN_MIN


@pytest.mark.parametrize("kernel", list(KernelKind))
@pytest.mark.parametrize("n", SIZES)
def test_every_window_size_works_for_color_and_gray(n, kernel):
    for shape in ((48, 64, 3), (48, 64)):
        img = noisy(shape)
        low = lowpass(img, n, kernel)
        assert low.shape == img.shape and low.dtype == np.uint8
        for view in HighpassView:
            high = highpass(img, n, kernel, view, gain=4)
            assert high.shape == img.shape and high.dtype == np.uint8


@pytest.mark.parametrize("kernel", list(KernelKind))
def test_constant_image(kernel):
    img = np.full((40, 40, 3), 100, np.uint8)
    for n in (3, 8, 30):
        assert np.abs(lowpass(img, n, kernel).astype(int) - 100).max() <= 1
        assert highpass(img, n, kernel, HighpassView.ABS).max() <= 1
        off = highpass(img, n, kernel, HighpassView.OFFSET, gain=4)
        assert np.abs(off.astype(int) - 128).max() <= 1


def test_highpass_n3_box_matches_lecture_kernel():
    """ФВЧ усереднення 3×3 = (1/9)·[[-1,-1,-1],[-1,8,-1],[-1,-1,-1]] зі слайдів."""
    img = noisy((40, 50), seed=3)
    kernel = np.array([[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]], np.float32) / 9
    exact = np.abs(cv2.filter2D(img.astype(np.float32), -1, kernel))
    ours = highpass(img, 3, KernelKind.BOX, HighpassView.ABS, gain=1)
    assert np.abs(ours.astype(np.float32) - np.clip(exact, 0, 255)).max() < 1.0


@pytest.mark.parametrize("kernel", list(KernelKind))
def test_lowpass_reduces_noise_with_larger_window(kernel):
    img = noisy((120, 160), seed=1)
    stds = [lowpass(img, n, kernel).std() for n in (3, 5, 9, 15, 29)]
    assert all(a > b for a, b in zip(stds, stds[1:], strict=False))


def test_highpass_responds_to_edge_not_flat_area():
    img = np.zeros((60, 60), np.uint8)
    img[:, 30:] = 200
    high = highpass(img, 5, KernelKind.BOX, HighpassView.ABS, gain=1)
    assert high[:, 28:32].max() > 50
    assert high[:, :10].max() == 0 and high[:, 50:].max() == 0


@pytest.mark.parametrize("flt", list(FilterMode))
@pytest.mark.parametrize("n", (3, 10, 30))
def test_mono_mode_result_has_equal_channels(flt, n):
    frame = noisy()
    p = Params(color=ColorMode.MONO, filter=flt, size=n)
    _, res = process_pair(frame, p)
    assert res.shape == (48, 64, 3)
    assert np.array_equal(res[..., 0], res[..., 1])
    assert np.array_equal(res[..., 1], res[..., 2])


@pytest.mark.parametrize("color", list(ColorMode))
@pytest.mark.parametrize("flt", list(FilterMode))
def test_original_is_never_modified(color, flt):
    """«Оригінал» — справжній кадр камери: на нього не впливають ні монохром, ні фільтри."""
    frame = noisy(seed=7)
    before = frame.copy()
    original, _ = process_pair(frame, Params(color=color, filter=flt, size=9))
    assert np.array_equal(original, before)
    assert not np.array_equal(original[..., 0], original[..., 1])  # залишається кольоровим
    assert np.array_equal(frame, before)  # вхідний масив не змінено


def test_color_mode_keeps_color_and_none_is_passthrough():
    frame = noisy(seed=5)
    p = Params(color=ColorMode.COLOR, filter=FilterMode.NONE)
    assert np.array_equal(process(frame, p), frame)
    res = process(frame, p.with_(filter=FilterMode.LOWPASS))
    assert not np.array_equal(res[..., 0], res[..., 1])


def test_output_is_bgr_uint8_for_all_modes():
    frame = noisy()
    for color in ColorMode:
        for flt in FilterMode:
            out = process(frame, Params(color=color, filter=flt))
            assert out.shape == frame.shape and out.dtype == np.uint8
