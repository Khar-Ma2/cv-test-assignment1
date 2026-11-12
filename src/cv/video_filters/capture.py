"""Потік захоплення й обробки відео: камера → фільтр → QImage для GUI."""

import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .filters import process_pair
from .sources import SourceSpec, make_source
from .state import Params

DEFAULT_OUTPUT_DIR = Path.home() / "Videos" / "cv-filters"
LOST_AFTER_FAILED_READS = 30


def to_qimage(bgr: np.ndarray) -> QImage:
    """Копія кадра BGR як QImage (володіє своїми даними, безпечна між потоками)."""
    bgr = np.ascontiguousarray(bgr)
    h, w = bgr.shape[:2]
    return QImage(bgr.data, w, h, bgr.strides[0], QImage.Format.Format_BGR888).copy()


class CaptureWorker(QThread):
    frame_ready = Signal(QImage, float, float)  # кадр, мс обробки, FPS
    opened = Signal(int, int)  # ширина, висота
    error = Signal(str)  # проблема з джерелом (показується в області відео)
    notice = Signal(str)  # коротке повідомлення (тост)
    saved = Signal(str)  # шлях збереженого файлу
    recording_started = Signal(str)
    recording_stopped = Signal()  # запис завершено (за запитом, через помилку або зупинку потоку)

    def __init__(
        self,
        spec: SourceSpec,
        params: Params,
        output_dir: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._spec = spec
        self._params = params
        self._out = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self._stop = threading.Event()
        self._busy = False  # GUI ще не обробив попередній кадр → пропускаємо
        self._snap_req = False
        self._record_req = False
        self._writer: cv2.VideoWriter | None = None
        self._record_path: Path | None = None
        self._fps = 0.0

    # ---- керування з GUI-потоку -------------------------------------------------
    def set_params(self, params: Params) -> None:
        self._params = params  # присвоєння посилання атомарне

    def request_snapshot(self) -> None:
        self._snap_req = True

    def set_recording(self, on: bool) -> None:
        self._record_req = on

    def frame_consumed(self) -> None:
        self._busy = False

    def stop(self) -> None:
        self._stop.set()

    # ---- потік ----------------------------------------------------------------
    def run(self) -> None:
        while not self._stop.is_set():
            src = make_source(self._spec)
            if not src.open():
                self.error.emit("Не вдалося відкрити джерело відео.\nПеревірте підключення камери.")
                self._sleep(1.0)
                continue
            try:
                self._loop(src)
            finally:
                self._finish_recording()
                src.release()
            if not self._stop.is_set():
                self._sleep(1.0)

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while not self._stop.is_set() and time.monotonic() < end:
            self.msleep(50)

    def _loop(self, src) -> None:
        announced = False
        fails = 0
        last = time.perf_counter()
        self._fps = 0.0
        while not self._stop.is_set():
            frame = src.read()
            if frame is None:
                fails += 1
                if fails >= LOST_AFTER_FAILED_READS:
                    self.error.emit("Втрачено сигнал з камери.\nСпроба відновити з'єднання…")
                    return
                self.msleep(30)
                continue
            fails = 0
            if not announced:
                self.opened.emit(frame.shape[1], frame.shape[0])
                announced = True

            t0 = time.perf_counter()
            p = self._params
            shown, result = process_pair(frame, p)
            display = np.hstack((shown, result)) if p.compare else result
            ms = (time.perf_counter() - t0) * 1000.0

            self._handle_snapshot(result)
            self._handle_recording(result, src.fps)

            now = time.perf_counter()
            inst = 1.0 / max(now - last, 1e-6)
            last = now
            self._fps = inst if self._fps == 0.0 else 0.9 * self._fps + 0.1 * inst

            if not self._busy:
                self._busy = True
                self.frame_ready.emit(to_qimage(display), ms, self._fps)

    # ---- знімок і запис ---------------------------------------------------------
    def _unique_path(self, prefix: str, ext: str) -> Path:
        self._out.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = self._out / f"{prefix}_{stamp}.{ext}"
        n = 1
        while path.exists():
            path = self._out / f"{prefix}_{stamp}_{n}.{ext}"
            n += 1
        return path

    def _handle_snapshot(self, result: np.ndarray) -> None:
        if not self._snap_req:
            return
        self._snap_req = False
        path = self._unique_path("snapshot", "png")
        if cv2.imwrite(str(path), result):
            self.saved.emit(str(path))
        else:
            self.notice.emit("Не вдалося зберегти знімок.")

    def _handle_recording(self, result: np.ndarray, src_fps: float) -> None:
        if self._record_req and self._writer is None:
            path = self._unique_path("record", "mp4")
            h, w = result.shape[:2]
            fps = max(5.0, min(60.0, self._fps or src_fps))
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter.fourcc(*"mp4v"), fps, (w, h))
            if writer.isOpened():
                self._writer, self._record_path = writer, path
                self.recording_started.emit(str(path))
            else:
                writer.release()
                self._record_req = False
                self.notice.emit("Не вдалося почати запис відео.")
                self.recording_stopped.emit()
        if self._writer is not None:
            self._writer.write(result)
            if not self._record_req:
                self._finish_recording()

    def _finish_recording(self) -> None:
        if self._writer is None:
            return
        self._writer.release()
        self._writer = None
        if self._record_path is not None:
            self.saved.emit(str(self._record_path))
        self._record_path = None
        self.recording_stopped.emit()
