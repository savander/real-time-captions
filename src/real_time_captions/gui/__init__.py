import signal
import sys
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .subtitle_window import SubtitleWindow


def run_gui(
    language: str | None,
    model_size_override: Optional[str] = None,
    force_cpu: bool = False,
    max_cpu_ram_gb: Optional[int] = None,
    task: str = "translate",
):
    """
    Entry point to start the subtitle overlay.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = SubtitleWindow(
        language,
        model_size_override=model_size_override,
        force_cpu=force_cpu,
        max_cpu_ram_gb=max_cpu_ram_gb,
        task=task,
    )
    window.show()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("Ctrl+C detected. Exiting application.")
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)

    timer = QTimer()
    timer.start(100)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec())
