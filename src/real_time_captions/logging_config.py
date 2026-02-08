import json
import logging
import sys

from rich.console import Console
from rich.logging import RichHandler

APP_NAME = "AutoCaptions"
APP_AUTHOR = "Codrig"


class GuiLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = {
                "type": "log",
                "level": record.levelname,
                "name": record.name,
                "message": self.format(record),
                "timestamp": record.created,
                "module": record.module,
                "funcName": record.funcName,
                "lineno": record.lineno,
            }
            if record.exc_info:
                log_entry["exc_info"] = self.format(record).split("\n", 1)[1:]

            print(json.dumps(log_entry), flush=True)
        except Exception:
            self.handleError(record)


def setup_logging(
    app_name: str = APP_NAME,
    app_author: str = APP_AUTHOR,
    is_worker_process: bool = False,
) -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    root_logger.setLevel(logging.INFO)

    if is_worker_process:
        if sys.stdout.isatty():
            console_handler = RichHandler(
                level=logging.INFO,
                console=Console(
                    stderr=True, force_terminal=True
                ),
                markup=True,
                show_time=True,
                show_level=True,
                show_path=False,
                enable_link_path=False,
                tracebacks_show_locals=False,
                log_time_format="%H:%M:%S",
            )
            root_logger.addHandler(console_handler)
            logger = logging.getLogger(__name__)
            logger.info("Worker logging configured for direct Rich console output.")
        else:
            gui_log_handler = GuiLogHandler()
            gui_log_handler.setFormatter(
                logging.Formatter(
                    "%(message)s"
                )
            )
            root_logger.addHandler(gui_log_handler)
            logger = logging.getLogger(__name__)
            logger.info("Worker logging configured to send JSON messages to GUI.")
    else:
        console_handler = RichHandler(
            level=logging.INFO,
            console=Console(stderr=True),
            markup=True,
            show_time=True,
            show_level=True,
            show_path=False,
            enable_link_path=False,
            tracebacks_show_locals=False,
            log_time_format="%H:%M:%S",
        )
        root_logger.addHandler(console_handler)
        logger = logging.getLogger(__name__)
        logger.info("GUI logging configured to rich console.")
