"""Джерела кадрів: камера (V4L2), відеофайл і синтетичний тестовий сигнал."""

import math
import sys
import time
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

SYNTHETIC = "synthetic"
FRAME_W, FRAME_H, FRAME_FPS = 640, 480, 30

SourceSpec = int | str


class FrameSource(Protocol):
    fps: float

    def open(self) -> bool: ...
    def read(self) -> np.ndarray | None: ...
    def release(self) -> None: ...


def list_cameras() -> list[tuple[str, int]]:
    """Камери системи: (підпис, індекс). На Linux беремо лише основні вузли відеозахоплення."""
    base = Path("/sys/class/video4linux")
    if not base.is_dir():
        return [] if sys.platform.startswith("linux") else [("Камера 0", 0)]
    found: list[tuple[str, int]] = []
    for node in sorted(base.glob("video*"), key=lambda p: int(p.name.removeprefix("video") or 0)):
        try:
            if (node / "index").read_text().strip() != "0":
                continue  # метаданні та додаткові вузли тієї ж камери
            name = (node / "name").read_text().strip().split(":")[0].replace("_", " ")
        except OSError:
            continue
        found.append((f"{name} · /dev/{node.name}", int(node.name.removeprefix("video"))))
    return found


class CameraSource:
    """Камера за індексом або відеофайл за шляхом."""

    def __init__(self, spec: SourceSpec):
        self.spec = spec
        self.fps = float(FRAME_FPS)
        self._cap: cv2.VideoCapture | None = None
        self._is_file = isinstance(spec, str)
        self._frame_dt = 0.0
        self._next = 0.0

    def open(self) -> bool:
        if isinstance(self.spec, int) and sys.platform.startswith("linux"):
            cap = cv2.VideoCapture(self.spec, cv2.CAP_V4L2)
        else:
            cap = cv2.VideoCapture(self.spec)
        if not cap.isOpened():
            cap.release()
            return False
        if not self._is_file:
            # MJPG + 640×480 — плавні 30 кадр/с на більшості вебкамер
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
            cap.set(cv2.CAP_PROP_FPS, FRAME_FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if 1.0 <= fps <= 240.0:
            self.fps = float(fps)
        self._frame_dt = 1.0 / self.fps if self._is_file else 0.0
        self._cap = cap
        return True

    def read(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok and self._is_file:  # кінець файлу — починаємо спочатку
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if self._frame_dt:  # файл читається миттєво — тримаємо темп
            now = time.perf_counter()
            if self._next > now:
                time.sleep(self._next - now)
            self._next = max(now, self._next) + self._frame_dt
        return frame if ok else None

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class SyntheticSource:
    """Тестовий сигнал із дрібними деталями, на яких добре видно роботу фільтрів."""

    def __init__(self, width: int = FRAME_W, height: int = FRAME_H, fps: float = FRAME_FPS):
        self.w, self.h, self.fps = width, height, float(fps)
        self._t0 = 0.0
        self._n = 0
        self._base: np.ndarray | None = None
        self._rng = np.random.default_rng(1)

    def open(self) -> bool:
        self._t0 = time.perf_counter()
        self._n = 0
        self._base = self._make_base()
        return True

    def _make_base(self) -> np.ndarray:
        w, h = self.w, self.h
        hsv = np.zeros((h, w, 3), np.uint8)
        hsv[..., 0] = np.linspace(0, 170, w, dtype=np.uint8)[None, :]
        hsv[..., 1] = 170
        hsv[..., 2] = np.linspace(230, 90, h, dtype=np.uint8)[:, None]
        base = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        # шахівниця та лінії різної частоти
        cell = 8
        yy, xx = np.mgrid[0 : h // 3, 0 : w // 3]
        checker = (((xx // cell) + (yy // cell)) % 2 * 255).astype(np.uint8)
        base[h - h // 3 :, : w // 3] = checker[..., None]
        for i, step in enumerate((2, 4, 8, 16)):
            x0 = w - w // 3 + i * (w // 12)
            for x in range(x0, x0 + w // 12 - 4, step):
                cv2.line(base, (x, 20), (x, h // 3), (255, 255, 255), 1)
        cv2.putText(
            base,
            "CV LAB",
            (w // 2 - 120, h // 2 + 10),
            cv2.FONT_HERSHEY_DUPLEX,
            2.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            base,
            "low-pass / high-pass",
            (w // 2 - 130, h // 2 + 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        return base

    def read(self) -> np.ndarray | None:
        if self._base is None:
            return None
        # тримаємо темп ≈ fps
        due = self._t0 + self._n / self.fps
        now = time.perf_counter()
        if due > now:
            time.sleep(due - now)
        t = self._n / self.fps
        self._n += 1
        frame = self._base.copy()
        cx = int(self.w * (0.5 + 0.35 * math.sin(t * 0.9)))
        cy = int(self.h * (0.5 + 0.3 * math.cos(t * 1.3)))
        cv2.circle(frame, (cx, cy), 46, (40, 40, 240), -1, cv2.LINE_AA)
        cv2.rectangle(frame, (cx - 70, cy - 20), (cx - 20, cy + 40), (30, 220, 255), 3)
        noise = self._rng.normal(0, 7, frame.shape)
        return np.clip(frame + noise, 0, 255).astype(np.uint8)

    def release(self) -> None:
        self._base = None


def make_source(spec: SourceSpec) -> FrameSource:
    if spec == SYNTHETIC:
        return SyntheticSource()
    return CameraSource(spec)


def parse_spec(text: str) -> SourceSpec:
    """'0' → 0, 'synthetic' → 'synthetic', інакше — шлях до відеофайлу."""
    return int(text) if text.isdigit() else text
