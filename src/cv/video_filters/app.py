"""Точка входу: ``python -m cv.video_filters`` або ``cv-filters``."""

import argparse
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .sources import SYNTHETIC, parse_spec
from .theme import stylesheet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-filters",
        description="Відео з камери з цифровими фільтрами низьких і високих частот.",
    )
    parser.add_argument(
        "--source",
        default=None,
        help=f"індекс камери (0, 1, …), шлях до відеофайлу або «{SYNTHETIC}» (тестовий сигнал)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args, qt_args = build_parser().parse_known_args(argv)
    app = QApplication([sys.argv[0], *qt_args])
    app.setStyle("Fusion")
    app.setApplicationName("Відеофільтри ФНЧ/ФВЧ")
    app.setStyleSheet(stylesheet())

    source = parse_spec(args.source) if args.source is not None else None
    window = MainWindow(source=source)
    window.show()
    app.aboutToQuit.connect(window.shutdown)

    # Ctrl+C у терміналі закриває вікно штатно (потік зупиняється, запис завершується)
    signal.signal(signal.SIGINT, lambda *_: app.closeAllWindows())
    keep_python_alive = QTimer()
    keep_python_alive.start(200)
    keep_python_alive.timeout.connect(lambda: None)  # дає інтерпретатору обробити сигнал
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
