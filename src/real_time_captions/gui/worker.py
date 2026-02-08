import json
import logging
import subprocess
import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    text_received = pyqtSignal(str)
    status_received = pyqtSignal(str)
    error_received = pyqtSignal(str)
    log_received = pyqtSignal(dict)

    def __init__(self, cmd_args: list[str]):
        super().__init__()
        self._cmd_args = cmd_args
        self._process: Optional[subprocess.Popen] = None
        self._is_running = True
        self._stdout_reader_thread: Optional[threading.Thread] = None
        self._stderr_reader_thread: Optional[threading.Thread] = None

    def run(self):
        try:
            self._process = subprocess.Popen(
                self._cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            if self._process.stdout is None or self._process.stderr is None:
                self.error_received.emit(
                    "Internal Error: stdout or stderr pipe is None"
                )
                return

            self._stdout_reader_thread = threading.Thread(
                target=self._read_stdout, daemon=True
            )
            self._stderr_reader_thread = threading.Thread(
                target=self._read_stderr, daemon=True
            )

            self._stdout_reader_thread.start()
            self._stderr_reader_thread.start()

            while self._is_running and self._process.poll() is None:
                self.msleep(10)

        except Exception as e:
            self.error_received.emit(f"GUI Worker Thread Error: {e}")
            logger.exception("Error in GUI Worker Thread:")
        finally:
            self.stop()

    def _read_stdout(self):
        while self._is_running:
            current_process = self._process
            if current_process is None or current_process.stdout is None:
                break

            line = current_process.stdout.readline()
            if line:
                self._process_line(line)
            else:
                if current_process.poll() is None:
                    self.msleep(1)
                else:
                    break
        logger.debug("Stdout reader stopped.")

    def _read_stderr(self):
        while self._is_running:
            current_process = self._process
            if current_process is None or current_process.stderr is None:
                break

            err_line = current_process.stderr.readline()
            if err_line:
                logger.error(f"[red]Worker Process Stderr:[/red] {err_line.strip()}")
            else:
                if current_process.poll() is None:
                    self.msleep(1)
                else:
                    break
        logger.debug("Stderr reader stopped.")

    def _process_line(self, line: str):
        try:
            data = json.loads(line.strip())
            match data:
                case {"type": "text", "content": content}:
                    self.text_received.emit(content)
                case {"type": "status", "content": content}:
                    self.status_received.emit(content)
                case {"type": "error", "content": content}:
                    self.error_received.emit(content)
                case {"type": "log", **log_record_data}:
                    self.log_received.emit(log_record_data)
                case _:
                    logger.warning(
                        f"GUI Worker: Received unexpected JSON type from worker: {data}"
                    )
        except json.JSONDecodeError:
            logger.warning(
                f"GUI Worker: Received non-JSON stdout from worker: {line.strip()}"
            )
        except Exception as e:
            logger.exception(f"GUI Worker: Error processing line: {line.strip()}")
            self.error_received.emit(f"Internal Worker Error: {e}")

    def stop(self):
        self._is_running = False
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

        if self._stdout_reader_thread and self._stdout_reader_thread.is_alive():
            self._stdout_reader_thread.join(timeout=1)
        if self._stderr_reader_thread and self._stderr_reader_thread.is_alive():
            self._stderr_reader_thread.join(timeout=1)
