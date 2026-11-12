"""Головне вікно: відео ліворуч, панель керування праворуч."""

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .capture import CaptureWorker
from .sources import SYNTHETIC, SourceSpec, list_cameras
from .state import (
    GAIN_MAX,
    GAIN_MIN,
    WIN_MAX,
    WIN_MIN,
    ColorMode,
    FilterMode,
    HighpassView,
    KernelKind,
    Params,
    clamp_window,
)
from .widgets import Card, KeyCap, Segmented, VideoView

PANEL_WIDTH = 340


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    return label


class MainWindow(QMainWindow):
    def __init__(
        self,
        source: SourceSpec | None = None,
        output_dir: Path | None = None,
        autostart: bool = True,
    ):
        super().__init__()
        self.setWindowTitle("Відеофільтри · ФНЧ / ФВЧ")
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        self.resize(
            min(1260, avail.width() - 40) if avail else 1260,
            min(860, avail.height() - 60) if avail else 860,
        )
        self.setMinimumSize(900, 600)

        self.params = Params()
        self._output_dir = output_dir
        self._worker: CaptureWorker | None = None
        self._resolution = (0, 0)
        self._last_stats = 0.0
        self._rec_requested = False
        self._rec_started = 0.0
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(500)
        self._rec_timer.timeout.connect(self._tick_recording)

        self._build_ui()
        self._fill_sources(source)
        self._sync_ui()
        self.setFocus()
        # клавіші працюють незалежно від того, який елемент має фокус
        QApplication.instance().installEventFilter(self)
        if autostart:
            self.start_source(self.source_combo.currentData())

    # ---- побудова інтерфейсу ------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(10)
        self.view = VideoView()
        left.addWidget(self.view, 1)
        self.stats = QLabel("—")
        self.stats.setObjectName("stats")
        left.addWidget(self.stats)
        layout.addLayout(left, 1)

        panel = QWidget()
        panel.setObjectName("root")
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 4, 0)
        column.setSpacing(14)
        column.addWidget(self._source_card())
        column.addWidget(self._display_card())
        column.addWidget(self._filter_card())
        column.addWidget(self._window_card())
        column.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # «Дії» закріплені внизу й завжди видимі; решта карток прокручується
        right = QWidget()
        right.setFixedWidth(PANEL_WIDTH)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(scroll, 1)
        right_layout.addWidget(self._actions_card())
        layout.addWidget(right)

    def _source_card(self) -> Card:
        card = Card("Джерело")
        self.source_combo = QComboBox()
        self.source_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.source_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_combo.activated.connect(self._on_source_chosen)
        card.body.addWidget(self.source_combo)
        return card

    def _display_card(self) -> Card:
        card = Card("Відображення")
        self.seg_color = Segmented([("Кольорове", ColorMode.COLOR), ("Монохромне", ColorMode.MONO)])
        self.seg_color.changed.connect(lambda v: self._apply(color=v))
        card.body.addWidget(self.seg_color)
        self.seg_compare = Segmented([("Один екран", False), ("Поруч", True)])
        self.seg_compare.changed.connect(lambda v: self._apply(compare=v))
        card.body.addWidget(self.seg_compare)
        return card

    def _filter_card(self) -> Card:
        card = Card("Фільтр")
        self.seg_filter = Segmented(
            [
                ("Без фільтра", FilterMode.NONE),
                ("ФНЧ", FilterMode.LOWPASS),
                ("ФВЧ", FilterMode.HIGHPASS),
            ]
        )
        self.seg_filter.changed.connect(lambda v: self._apply(filter=v))
        card.body.addWidget(self.seg_filter)

        self.kernel_caption = _caption("Ядро")
        card.body.addWidget(self.kernel_caption)
        self.seg_kernel = Segmented(
            [("Усереднення", KernelKind.BOX), ("Гаусове", KernelKind.GAUSS)]
        )
        self.seg_kernel.changed.connect(lambda v: self._apply(kernel=v))
        card.body.addWidget(self.seg_kernel)

        self.hp_caption = _caption("Відображення ФВЧ")
        card.body.addWidget(self.hp_caption)
        self.seg_hp = Segmented([("Модуль", HighpassView.ABS), ("Зсув 128", HighpassView.OFFSET)])
        self.seg_hp.changed.connect(lambda v: self._apply(hp_view=v))
        card.body.addWidget(self.seg_hp)

        row = QHBoxLayout()
        self.gain_caption = _caption("Підсилення")
        row.addWidget(self.gain_caption)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(GAIN_MIN, GAIN_MAX)
        self.gain_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gain_slider.valueChanged.connect(lambda v: self._apply(gain=v))
        row.addWidget(self.gain_slider, 1)
        self.gain_value = QLabel()
        self.gain_value.setMinimumWidth(30)
        self.gain_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.gain_value)
        card.body.addLayout(row)
        return card

    def _window_card(self) -> Card:
        card = Card("Вікно фільтра")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_minus = QPushButton("−")
        self.btn_plus = QPushButton("+")
        for button, step, tip in (
            (self.btn_minus, -1, "Зменшити вікно на 1 (клавіша 8)"),
            (self.btn_plus, +1, "Збільшити вікно на 1 (клавіша 9)"),
        ):
            button.setObjectName("step")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, s=step: self.set_window(self.params.size + s))
        row.addWidget(KeyCap("8"))
        row.addWidget(self.btn_minus)
        row.addStretch(1)
        self.badge = QLabel()
        self.badge.setObjectName("sizeBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.badge)
        row.addStretch(1)
        row.addWidget(self.btn_plus)
        row.addWidget(KeyCap("9"))
        card.body.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(WIN_MIN, WIN_MAX)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.valueChanged.connect(self.set_window)
        card.body.addWidget(self.slider)

        self.window_hint = _caption("")
        self.window_hint.setWordWrap(True)
        self.window_hint.setMinimumHeight(34)
        self.window_hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        card.body.addWidget(self.window_hint)
        return card

    def _actions_card(self) -> Card:
        card = Card("Дії")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_snapshot = QPushButton("Знімок · S")
        self.btn_snapshot.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_snapshot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snapshot.clicked.connect(self.snapshot)
        self.btn_record = QPushButton("● Запис · R")
        self.btn_record.setObjectName("record")
        self.btn_record.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_record.clicked.connect(self.toggle_recording)
        row.addWidget(self.btn_snapshot, 1)
        row.addWidget(self.btn_record, 1)
        card.body.addLayout(row)
        return card

    # ---- джерела ----------------------------------------------------------------
    def _fill_sources(self, source: SourceSpec | None) -> None:
        cameras = list_cameras()
        for label, index in cameras:
            self.source_combo.addItem(label, index)
        self.source_combo.addItem("Тестовий сигнал", SYNTHETIC)
        if source is not None:
            pos = self.source_combo.findData(source)
            if pos < 0:
                self.source_combo.addItem(f"Файл · {Path(str(source)).name}", source)
                pos = self.source_combo.count() - 1
            self.source_combo.setCurrentIndex(pos)
        elif not cameras:
            self.source_combo.setCurrentIndex(self.source_combo.findData(SYNTHETIC))
            self.view.show_toast("Камеру не знайдено — показано тестовий сигнал", 6000)

    def _on_source_chosen(self, _index: int) -> None:
        self.start_source(self.source_combo.currentData())
        self.setFocus()

    def start_source(self, spec: SourceSpec) -> None:
        self._stop_worker()
        self.view.set_message("Підключення до джерела…")
        worker = CaptureWorker(spec, self.params, self._output_dir, self)
        worker.frame_ready.connect(self._on_frame)
        worker.opened.connect(self._on_opened)
        worker.error.connect(self._on_error)
        worker.notice.connect(self.view.show_toast)
        worker.saved.connect(self._on_saved)
        worker.recording_started.connect(self._on_recording_started)
        worker.recording_stopped.connect(self._on_recording_stopped)
        self._worker = worker
        worker.start()

    def _stop_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.stop()
            worker.wait(5000)
        self._on_recording_stopped()

    # ---- стан і синхронізація -----------------------------------------------------
    def set_window(self, n: int) -> None:
        """Єдина точка зміни розміру вікна фільтра (слайдер, кнопки, клавіші 8/9)."""
        self._apply(size=clamp_window(n))

    def _apply(self, **changes) -> None:
        self.params = self.params.with_(**changes)
        if self._worker is not None:
            self._worker.set_params(self.params)
        self._sync_ui()

    def _sync_ui(self) -> None:
        p = self.params
        n = p.size
        for widget, value in (
            (self.slider, n),
            (self.gain_slider, p.gain),
        ):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.seg_color.set_value(p.color)
        self.seg_compare.set_value(p.compare)
        self.seg_filter.set_value(p.filter)
        self.seg_kernel.set_value(p.kernel)
        self.seg_hp.set_value(p.hp_view)

        self.badge.setText(f"{n}×{n}")
        hint = f"Діапазон {WIN_MIN}–{WIN_MAX} · клавіші 8 / 9"
        if n % 2 == 0:
            hint += "\nПарне вікно: ядро зсунуте на ½ пікселя"
        self.window_hint.setText(hint)
        self.gain_value.setText(f"×{p.gain}")

        has_filter = p.filter is not FilterMode.NONE
        is_hp = p.filter is FilterMode.HIGHPASS
        for widget in (self.kernel_caption, self.seg_kernel):
            widget.setEnabled(has_filter)
        for widget in (
            self.hp_caption,
            self.seg_hp,
            self.gain_caption,
            self.gain_slider,
            self.gain_value,
        ):
            widget.setEnabled(is_hp)

        self.view.set_compare(p.compare)
        self.view.set_hud(self._hud_text())

    def _hud_text(self) -> str:
        p = self.params
        parts = ["Колір" if p.color is ColorMode.COLOR else "Моно"]
        if p.filter is FilterMode.NONE:
            parts.append("без фільтра")
        else:
            name = "ФНЧ" if p.filter is FilterMode.LOWPASS else "ФВЧ"
            kernel = "усереднення" if p.kernel is KernelKind.BOX else "гаусове"
            parts += [f"{name} {kernel}", f"{p.size}×{p.size}"]
        return " · ".join(parts)

    # ---- сигнали потоку --------------------------------------------------------
    def _on_frame(self, image: QImage, ms: float, fps: float) -> None:
        self.view.set_frame(image)
        if self._worker is not None:
            self._worker.frame_consumed()
        now = time.monotonic()
        if now - self._last_stats >= 0.25:
            self._last_stats = now
            w, h = self._resolution
            self.stats.setText(f"{w}×{h}  ·  {fps:.1f} FPS  ·  обробка {ms:.1f} мс")

    def _on_opened(self, w: int, h: int) -> None:
        self._resolution = (w, h)
        self.view.set_message("")

    def _on_error(self, text: str) -> None:
        self.view.set_message(text)
        self.stats.setText("Немає сигналу")

    def _on_saved(self, path: str) -> None:
        self.view.show_toast(f"Збережено: {path}", 6000)

    # ---- знімок і запис -------------------------------------------------------------
    def snapshot(self) -> None:
        if self._worker is not None:
            self._worker.request_snapshot()

    def toggle_recording(self) -> None:
        if self._worker is None:
            return
        self._rec_requested = not self._rec_requested
        self._worker.set_recording(self._rec_requested)
        if not self._rec_requested:
            self._on_recording_stopped()

    def _on_recording_started(self, _path: str) -> None:
        self._rec_requested = True
        self._rec_started = time.monotonic()
        self._set_record_button(True)
        self._rec_timer.start()
        self._tick_recording()

    def _on_recording_stopped(self) -> None:
        self._rec_requested = False
        self._rec_timer.stop()
        self.view.set_recording("")
        self._set_record_button(False)

    def _set_record_button(self, recording: bool) -> None:
        self.btn_record.setProperty("recording", recording)
        self.btn_record.setText("■ Стоп · R" if recording else "● Запис · R")
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)

    def _tick_recording(self) -> None:
        elapsed = int(time.monotonic() - self._rec_started)
        self.view.set_recording(f"● REC {elapsed // 60:02d}:{elapsed % 60:02d}")

    # ---- клавіші ------------------------------------------------------------------
    def _handle_key(self, event: QKeyEvent) -> bool:
        key = event.key()
        if key == Qt.Key.Key_8:  # також цифрова клавіатура (Key_8 + KeypadModifier)
            self.set_window(self.params.size - 1)
        elif key == Qt.Key.Key_9:
            self.set_window(self.params.size + 1)
        elif key == Qt.Key.Key_S and not event.isAutoRepeat():
            self.snapshot()
        elif key == Qt.Key.Key_R and not event.isAutoRepeat():
            self.toggle_recording()
        else:
            return False
        return True

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(obj, QWidget)
            and obj.window() is self
            and not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
        ):
            return self._handle_key(event)
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._handle_key(event):
            super().keyPressEvent(event)

    def shutdown(self) -> None:
        """Зупинити потік (і завершити запис) та відключити перехоплення клавіш."""
        QApplication.instance().removeEventFilter(self)
        self._stop_worker()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
