"""Власні віджети: картка, сегментований перемикач, «кейкап», область відео."""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import color


class Card(QFrame):
    """Панель із заголовком; вміст додається в ``body``."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)
        label = QLabel(title.upper())
        label.setObjectName("cardTitle")
        outer.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body)


class KeyCap(QLabel):
    """Підказка клавіші у вигляді кейкапа."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("keycap")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class Segmented(QWidget):
    """Сегментований перемикач: рівно один варіант обрано."""

    changed = Signal(object)  # значення обраного варіанта (лише від дії користувача)

    def __init__(self, options: list[tuple[str, object]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._values: dict[int, object] = {}
        last = len(options) - 1
        for i, (label, value) in enumerate(options):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("seg", True)
            button.setProperty("pos", "first" if i == 0 else "last" if i == last else "mid")
            self._group.addButton(button, i)
            self._values[i] = value
            layout.addWidget(button, 1)
        self._group.idClicked.connect(lambda i: self.changed.emit(self._values[i]))

    def set_value(self, value: object) -> None:
        for i, v in self._values.items():
            if v == value:
                self._group.button(i).setChecked(True)
                return

    def value(self) -> object:
        return self._values[self._group.checkedId()]

    def button_for(self, value: object) -> QPushButton:
        for i, v in self._values.items():
            if v == value:
                return self._group.button(i)
        raise KeyError(value)


class VideoView(QWidget):
    """Кадр відео в закругленій рамці (letterbox) з HUD, підписами та тостами."""

    RADIUS = 14

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(480, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._image: QImage | None = None
        self._message = "Підключення до камери…"
        self._hud = ""
        self._rec = ""
        self._toast = ""
        self._compare = False
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)

    # ---- стан --------------------------------------------------------------
    def set_frame(self, image: QImage) -> None:
        self._image = image
        self.update()

    def set_message(self, text: str) -> None:
        self._message = text
        self.update()

    def set_hud(self, text: str) -> None:
        self._hud = text
        self.update()

    def set_recording(self, text: str) -> None:
        self._rec = text
        self.update()

    def set_compare(self, on: bool) -> None:
        self._compare = on
        self.update()

    def show_toast(self, text: str, ms: int = 3500) -> None:
        self._toast = text
        self._toast_timer.start(ms)
        self.update()

    def _clear_toast(self) -> None:
        self._toast = ""
        self.update()

    @property
    def message(self) -> str:
        return self._message

    # ---- малювання ---------------------------------------------------------
    def _chip(
        self,
        p: QPainter,
        text: str,
        anchor: QPointF,
        *,
        right: bool = False,
        bottom: bool = False,
        center: bool = False,
        bg: QColor | None = None,
        fg: QColor | None = None,
        bold: bool = True,
    ) -> None:
        font = QFont(self.font())
        font.setPointSizeF(9.5)
        font.setBold(bold)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = fm.horizontalAdvance(text) + 20
        h = fm.height() + 12
        x = anchor.x() - (w / 2 if center else w if right else 0)
        y = anchor.y() - (h if bottom else 0)
        rect = QRectF(x, y, w, h)
        fill = bg or QColor(10, 12, 16, 190)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(fg or color("text"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(outer, self.RADIUS, self.RADIUS)
        p.fillPath(clip, QColor("#090b0f"))

        shown = self._image is not None and not self._message
        target = QRectF()
        if shown:
            img = self._image
            scale = min(outer.width() / img.width(), outer.height() / img.height())
            tw, th = img.width() * scale, img.height() * scale
            target = QRectF(
                outer.x() + (outer.width() - tw) / 2, outer.y() + (outer.height() - th) / 2, tw, th
            )
            p.save()
            p.setClipPath(clip)
            p.drawImage(target, img)
            p.restore()
            if self._compare:
                mid = target.center().x()
                p.setPen(QPen(QColor(255, 255, 255, 90), 1))
                p.drawLine(QPointF(mid, target.top()), QPointF(mid, target.bottom()))
                self._chip(p, "ОРИГІНАЛ", QPointF(target.left() + 12, target.top() + 12))
                self._chip(p, "РЕЗУЛЬТАТ", QPointF(mid + 12, target.top() + 12))
        else:
            p.setPen(color("muted"))
            font = QFont(self.font())
            font.setPointSizeF(12)
            p.setFont(font)
            p.drawText(
                outer.adjusted(24, 24, -24, -24),
                Qt.AlignmentFlag.AlignCenter,
                self._message or "Немає сигналу",
            )

        p.setPen(QPen(color("border"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(outer, self.RADIUS, self.RADIUS)

        if shown and self._hud:
            self._chip(p, self._hud, QPointF(outer.left() + 14, outer.bottom() - 14), bottom=True)
        if self._rec:
            self._chip(
                p,
                self._rec,
                QPointF(outer.right() - 14, outer.top() + 14),
                right=True,
                bg=color("danger"),
                fg=QColor("white"),
            )
        if self._toast:
            self._chip(
                p,
                self._toast,
                QPointF(outer.center().x(), outer.bottom() - 58),
                center=True,
                bottom=True,
                bg=QColor(38, 44, 56, 235),
                bold=False,
            )
        p.end()
