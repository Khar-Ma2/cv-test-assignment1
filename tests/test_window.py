import cv2
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from cv.video_filters.main_window import MainWindow
from cv.video_filters.sources import SYNTHETIC
from cv.video_filters.state import WIN_MAX, WIN_MIN, ColorMode, FilterMode


@pytest.fixture
def idle(qtbot, tmp_path):
    """Вікно без потоку захоплення — для перевірки логіки керування."""
    w = MainWindow(source=SYNTHETIC, output_dir=tmp_path, autostart=False)
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def live(qtbot, tmp_path):
    """Вікно з синтетичним джерелом кадрів."""
    w = MainWindow(source=SYNTHETIC, output_dir=tmp_path)
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.view._image is not None and not w.view.message, timeout=8000)
    yield w
    w.close()


def press(qtbot, widget, key, times=1, mod=Qt.KeyboardModifier.NoModifier):
    for _ in range(times):
        qtbot.keyClick(widget, key, mod)


def test_keys_8_and_9_change_window_by_one(qtbot, idle):
    n = idle.params.size
    press(qtbot, idle, Qt.Key.Key_9)
    assert idle.params.size == n + 1
    press(qtbot, idle, Qt.Key.Key_8, 2)
    assert idle.params.size == n - 1
    assert idle.slider.value() == n - 1
    assert idle.badge.text() == f"{n - 1}×{n - 1}"


def test_window_is_clamped_to_3_and_30(qtbot, idle):
    press(qtbot, idle, Qt.Key.Key_9, 60)
    assert idle.params.size == WIN_MAX == idle.slider.value()
    press(qtbot, idle, Qt.Key.Key_8, 60)
    assert idle.params.size == WIN_MIN == idle.slider.value()


def test_every_size_in_range_is_reachable_with_step_one(qtbot, idle):
    press(qtbot, idle, Qt.Key.Key_8, 60)
    seen = [idle.params.size]
    for _ in range(WIN_MAX - WIN_MIN):
        press(qtbot, idle, Qt.Key.Key_9)
        seen.append(idle.params.size)
    assert seen == list(range(WIN_MIN, WIN_MAX + 1))


def test_numpad_keys_work(qtbot, idle):
    n = idle.params.size
    press(qtbot, idle, Qt.Key.Key_9, mod=Qt.KeyboardModifier.KeypadModifier)
    assert idle.params.size == n + 1
    press(qtbot, idle, Qt.Key.Key_8, 2, mod=Qt.KeyboardModifier.KeypadModifier)
    assert idle.params.size == n - 1


def test_keys_work_when_slider_or_combo_has_focus(qtbot, idle):
    n = idle.params.size
    idle.slider.setFocus()
    press(qtbot, idle.slider, Qt.Key.Key_9)
    assert idle.params.size == n + 1
    press(qtbot, idle.source_combo, Qt.Key.Key_8)
    assert idle.params.size == n


def test_slider_and_buttons_change_window(qtbot, idle):
    idle.slider.setValue(12)
    assert idle.params.size == 12 and idle.badge.text() == "12×12"
    idle.btn_plus.click()
    idle.btn_plus.click()
    idle.btn_minus.click()
    assert idle.params.size == 13


def test_controls_update_params_and_enabled_state(qtbot, idle):
    idle.seg_filter.button_for(FilterMode.HIGHPASS).click()
    assert idle.params.filter is FilterMode.HIGHPASS
    assert idle.seg_hp.isEnabled() and idle.gain_slider.isEnabled()
    idle.seg_filter.button_for(FilterMode.LOWPASS).click()
    assert not idle.seg_hp.isEnabled() and idle.seg_kernel.isEnabled()
    idle.seg_filter.button_for(FilterMode.NONE).click()
    assert not idle.seg_kernel.isEnabled()
    idle.seg_color.button_for(ColorMode.MONO).click()
    assert idle.params.color is ColorMode.MONO


def test_window_stays_valid_when_filter_changes(qtbot, idle):
    press(qtbot, idle, Qt.Key.Key_9, 5)
    size = idle.params.size
    idle.seg_filter.button_for(FilterMode.HIGHPASS).click()
    assert idle.params.size == size


def test_frames_arrive_and_compare_doubles_width(qtbot, live):
    width = live.view._image.width()
    assert width == 640
    live.seg_compare.button_for(True).click()
    qtbot.waitUntil(lambda: live.view._image.width() == 2 * width, timeout=5000)
    live.seg_compare.button_for(False).click()
    qtbot.waitUntil(lambda: live.view._image.width() == width, timeout=5000)


def test_mono_frames_are_gray_and_color_frames_are_not(qtbot, live):
    live.seg_filter.button_for(FilterMode.NONE).click()
    live.seg_color.button_for(ColorMode.MONO).click()

    def gray() -> bool:
        img = live.view._image
        return all(
            (c := img.pixelColor(x, y)).red() == c.green() == c.blue()
            for x, y in ((50, 50), (300, 200), (600, 400), (320, 100))
        )

    qtbot.waitUntil(gray, timeout=5000)
    live.seg_color.button_for(ColorMode.COLOR).click()
    qtbot.waitUntil(lambda: not gray(), timeout=5000)


def test_compare_original_stays_color_in_mono_mode(qtbot, live):
    live.seg_compare.button_for(True).click()
    live.seg_color.button_for(ColorMode.MONO).click()
    live.seg_filter.button_for(FilterMode.HIGHPASS).click()

    def halves_ok() -> bool:
        img = live.view._image
        if img.width() != 1280:
            return False
        points = ((50, 50), (300, 200), (600, 400))
        left_colored = any(
            not ((c := img.pixelColor(x, y)).red() == c.green() == c.blue()) for x, y in points
        )
        right_gray = all(
            (c := img.pixelColor(640 + x, y)).red() == c.green() == c.blue() for x, y in points
        )
        return left_colored and right_gray

    qtbot.waitUntil(halves_ok, timeout=5000)


def high_freq_energy(image) -> float:
    """Середня абсолютна різниця сусідніх пікселів кадра, що відображається."""
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    h, w = img.height(), img.width()
    raw = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())
    arr = raw[:, : w * 3].reshape(h, w, 3).astype(np.int16)
    return float(np.abs(np.diff(arr, axis=1)).mean())


def test_window_size_changes_the_picture(qtbot, live):
    live.seg_filter.button_for(FilterMode.LOWPASS).click()
    live.set_window(3)
    qtbot.wait(400)
    energy_small = high_freq_energy(live.view._image)
    live.set_window(30)
    qtbot.wait(400)
    energy_large = high_freq_energy(live.view._image)
    assert energy_large < 0.5 * energy_small


def test_snapshot_writes_png(qtbot, live, tmp_path):
    live.snapshot()
    qtbot.waitUntil(lambda: "snapshot_" in live.view._toast, timeout=5000)
    png = next(tmp_path.glob("snapshot_*.png"))
    img = cv2.imread(str(png))
    assert img is not None and img.shape == (480, 640, 3)


def test_snapshot_saves_result_only_even_in_compare_mode(qtbot, live, tmp_path):
    live.seg_compare.button_for(True).click()
    qtbot.waitUntil(lambda: live.view._image.width() == 1280, timeout=5000)
    live.snapshot()
    qtbot.waitUntil(lambda: "snapshot_" in live.view._toast, timeout=5000)
    assert cv2.imread(str(next(tmp_path.glob("snapshot_*.png")))).shape == (480, 640, 3)


def test_recording_writes_playable_video(qtbot, live, tmp_path):
    live.toggle_recording()
    qtbot.waitUntil(lambda: live.btn_record.property("recording") is True, timeout=5000)
    assert live.view._rec.startswith("● REC")
    qtbot.wait(700)
    live.toggle_recording()
    qtbot.waitUntil(lambda: live.btn_record.property("recording") is False, timeout=5000)
    # файл готовий, коли потік його закрив і повідомив про збереження
    qtbot.waitUntil(lambda: "record_" in live.view._toast, timeout=5000)
    path = next(tmp_path.glob("record_*.mp4"))
    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) >= 3
    cap.release()


def test_close_stops_worker(qtbot, live):
    worker = live._worker
    live.close()
    assert live._worker is None and not worker.isRunning()
