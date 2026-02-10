import io
import json
import logging
import os
import queue
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    sample_rate: int = 16000
    window_duration: int = 5
    overlap_duration: float = 0.5
    newline_interval: int = 15
    block_size: int = 4000
    encoding: str = "utf-8"
    model_size: str = "large-v3"
    beam_size: int = 5
    vad_filter: bool = True
    model_size_override: Optional[str] = None
    force_cpu: bool = False
    max_cpu_ram_gb: Optional[int] = None
    task: str = "translate"
    use_microphone: bool = False


class MessageHandler:
    @staticmethod
    def _send(msg_type: str, content: str) -> None:
        print(json.dumps({"type": msg_type, "content": content}), flush=True)

    @staticmethod
    def error(content: str) -> None:
        MessageHandler._send("error", content)

    @staticmethod
    def status(content: str) -> None:
        MessageHandler._send("status", content)

    @staticmethod
    def text(content: str) -> None:
        MessageHandler._send("text", content)


class TextUtils:
    @staticmethod
    def get_unique_suffix(old_text: str, new_text: str) -> str:
        old_words: List[str] = old_text.lower().split()
        new_words: List[str] = new_text.lower().split()

        if not old_words:
            return new_text

        min_len = min(len(old_words), len(new_words))
        for i in range(min_len, 0, -1):
            if old_words[-i:] == new_words[:i]:
                return " ".join(new_words[i:])

        return new_text


class AudioWorker:
    def __init__(
        self,
        language: Optional[str],
        config: WorkerConfig = WorkerConfig(),
        streamer_factory: Optional[Callable[[], Any]] = None,
        engine_factory: Optional[Callable[[], Any]] = None,
    ):
        logger.info("AudioWorker: Initializing...")
        self.config = config
        self.language = language
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.running = False

        self.buffer = np.array([], dtype=np.float32)
        self.window_size = config.sample_rate * config.window_duration
        self.overlap_samples = int(config.sample_rate * config.overlap_duration)

        self.last_full_text = ""
        self.last_newline_time = time.time()

        self.streamer: Optional[Any] = None
        self.engine: Optional[Any] = None

        self._streamer_factory = streamer_factory
        self._engine_factory = engine_factory

    def _setup_environment(self) -> None:
        logger.info("AudioWorker: Setting up environment...")
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding=self.config.encoding)

    def _load_modules(self) -> bool:
        try:
            from . import bootstrap

            logger.info("AudioWorker: Setting up CUDA runtime...")
            bootstrap.setup_cuda_runtime()

            if self._streamer_factory:
                self.streamer = self._streamer_factory()
            else:
                from .capture import AudioStreamer

                MessageHandler.status(
                    "Initializing Audio Streamer (It can take a while)..."
                )
                logger.info(
                    "AudioWorker: Initializing Audio Streamer (It can take a while)..."
                )
                self.streamer = AudioStreamer(
                    sample_rate=self.config.sample_rate,
                    use_microphone=self.config.use_microphone,
                )

            if self._engine_factory:
                MessageHandler.status("Using provided AI Model engine...")
                self.engine = self._engine_factory()
            else:
                from .transcriber import TranscriptionEngine

                MessageHandler.status("Loading AI Model (Transcription Engine)...")
                logger.info("AudioWorker: Loading Transcription Engine...")
                self.engine = TranscriptionEngine(
                    language=self.language,
                    model_size_override=self.config.model_size_override,
                    force_cpu=self.config.force_cpu,
                    max_cpu_ram_gb=self.config.max_cpu_ram_gb,
                    task=self.config.task,
                )

            return True

        except ImportError as e:
            MessageHandler.error(f"Import Error: {e}")
            logger.exception("Import error during module loading:")
        except Exception as e:
            MessageHandler.error(f"Init Error: {e}")
            logger.exception("General error during module loading:")

        return False

    def _audio_producer(self) -> None:
        warnings.filterwarnings("ignore", message=".*data discontinuity.*")

        if self.streamer is None:
            logger.error("AudioStreamer is not initialized in _audio_producer.")
            return

        try:
            for chunk in self.streamer.stream_audio(block_size=self.config.block_size):
                if not self.running:
                    logger.info("Audio producer stopping.")
                    break
                self.audio_queue.put(chunk)
        except Exception as e:
            logger.exception("Error in audio producer thread:")
            MessageHandler.error(f"Audio producer error: {e}")

    def _process_transcription(self, audio_chunk: np.ndarray) -> None:
        if self.engine is None:
            logger.error(
                "TranscriptionEngine is not initialized in _process_transcription."
            )
            return

        try:
            final_text = self.engine.transcribe(audio_chunk)
            if not final_text:
                return

            new_part = TextUtils.get_unique_suffix(self.last_full_text, final_text)
            if new_part:
                MessageHandler.text(new_part)
                self.last_full_text = final_text
        except Exception as e:
            logger.exception("Error during transcription process:")
            MessageHandler.error(f"Transcription error: {e}")

    def _check_newline_interval(self) -> None:
        if time.time() - self.last_newline_time > self.config.newline_interval:
            self.last_newline_time = time.time()
            self.last_full_text = ""
            logger.debug("Resetting last_full_text due to newline interval.")

    def _process_buffer(self) -> None:
        try:
            chunk = self.audio_queue.get(timeout=0.1)
            self.buffer = np.append(self.buffer, chunk)

            if len(self.buffer) >= self.window_size:
                audio_to_process = self.buffer.copy()
                self.buffer = self.buffer[-self.overlap_samples :]

                self._process_transcription(audio_to_process)
                self._check_newline_interval()
        except queue.Empty:
            pass
        except Exception as e:
            logger.exception("Error processing audio buffer:")
            MessageHandler.error(f"Buffer processing error: {e}")

    def run(self) -> None:
        self._setup_environment()

        if not self._load_modules():
            logger.critical("Failed to load necessary modules. Exiting worker.")
            return

        self.running = True
        threading.Thread(target=self._audio_producer, daemon=True).start()
        logger.info("Audio producer thread started.")

        MessageHandler.status("Ready. Listening...")
        logger.info("AudioWorker is ready and listening.")

        try:
            while self.running:
                self._process_buffer()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Stopping worker.")
            self.running = False
            sys.exit(0)
        except Exception as e:
            logger.exception("Unhandled exception in main worker loop:")
            MessageHandler.error(f"Unhandled worker error: {e}")
        finally:
            logger.info("AudioWorker has stopped.")


def run_worker_logic(
    language: Optional[str],
    model_size_override: Optional[str] = None,
    force_cpu: bool = False,
    max_cpu_ram_gb: Optional[int] = None,
    task: str = "translate",
    use_microphone: bool = False,
) -> None:
    logger.info("Starting AudioWorker logic.")
    config = WorkerConfig(
        model_size_override=model_size_override,
        force_cpu=force_cpu,
        max_cpu_ram_gb=max_cpu_ram_gb,
        task=task,
        use_microphone=use_microphone,
    )
    worker = AudioWorker(language, config=config)
    worker.run()
