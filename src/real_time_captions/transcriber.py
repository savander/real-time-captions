import io
import logging
import os
from contextlib import redirect_stderr
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

from real_time_captions.worker import MessageHandler

from .hardware_utils import (
    get_hardware_info,
    get_optimal_device_settings,
    get_optimal_model_size,
)

logger = logging.getLogger(__name__)


class TranscriptionEngine:
    def __init__(
        self,
        language: Optional[str] = None,
        model_size_override: Optional[str] = None,
        force_cpu: bool = False,
        max_cpu_ram_gb: Optional[int] = None,
        task: str = "translate",
    ) -> None:
        logger.info("TranscriptionEngine init start")
        self.language = language
        self.task = task

        if force_cpu:
            self.device = "cpu"
            self.compute_type = "int8"
            self.beam_size = 1
            self.vad_filter = True
            logger.info("CPU usage forced by user. Device: 'cpu', Compute Type: 'int8'")
            hardware_info = get_hardware_info()
            self.model_size = (
                model_size_override
                if model_size_override
                else get_optimal_model_size(
                    hardware_info, force_cpu=True, max_cpu_ram_gb=max_cpu_ram_gb
                )
            )
            logger.info(f"Using model size: '{self.model_size}' (CPU forced)")
        else:
            hardware_info = get_hardware_info()
            optimal_settings = get_optimal_device_settings(hardware_info)

            self.device = optimal_settings["device"]
            self.compute_type = optimal_settings["compute_type"]
            self.beam_size = optimal_settings["beam_size"]
            self.vad_filter = optimal_settings["vad_filter"]

            if model_size_override:
                self.model_size = model_size_override
                logger.info(f"Using model size from CLI override: '{self.model_size}'")
            else:
                self.model_size = get_optimal_model_size(
                    hardware_info, force_cpu=False, max_cpu_ram_gb=max_cpu_ram_gb
                )
                logger.info(f"Automatically selected model size: '{self.model_size}'")

            logger.info(f"Detected hardware: {hardware_info}")
            logger.info(
                f"Using optimal settings: device='{self.device}', compute_type='{self.compute_type}', beam_size='{self.beam_size}', vad_filter='{self.vad_filter}'"
            )

        logger.info(
            "Loading WhisperModel '%s' on %s with %s...",
            self.model_size,
            self.device,
            self.compute_type,
        )

        if self.model_size in ["tiny", "base", "small"] and self.language is None:
            logger.info(
                "\n"
                "[bold yellow]---------------------------[/bold yellow]\n"
                "[yellow]Recommendation: For smaller models (tiny, base, small), specifying the [bold cyan]--language[/bold cyan]\n"
                "argument (e.g., [bold cyan]--language en[/bold cyan]) can significantly improve transcription accuracy\n"
                "and performance, especially if your audio is not exclusively in English.[/yellow]\n"
                "[bold yellow]---------------------------[/bold yellow]"
            )

        try:
            hf_repo_id = self.model_size
            if "/" not in self.model_size and not os.path.exists(self.model_size):
                hf_repo_id = f"Systran/faster-whisper-{self.model_size}"

            MessageHandler.status(
                f"Preparing model '{self.model_size}' (downloading if not cached via {hf_repo_id})..."
            )
            logger.info(
                f"Attempting to get local path for model '{self.model_size}' (via {hf_repo_id}). Will download if not cached."
            )

            local_model_path = ""
            with redirect_stderr(io.StringIO()):
                local_model_path = snapshot_download(
                    repo_id=hf_repo_id, tqdm_class=None
                )

            MessageHandler.status(f"Loading model from local path: {local_model_path}")
            logger.info(
                f"Local model path determined: {local_model_path}. Instantiating WhisperModel."
            )

            self.model = WhisperModel(
                local_model_path, device=self.device, compute_type=self.compute_type
            )
            MessageHandler.status(
                f"Model '{self.model_size}' loaded successfully from: {local_model_path}!"
            )
            logger.info(f"WhisperModel loaded successfully from: {local_model_path}!")
        except Exception as e:
            logger.critical("CRITICAL ERROR inside WhisperModel init: %s", e)
            raise e

        logger.info(
            "TranscriptionEngine initialized with: "
            f"model_size='{self.model_size}', device='{self.device}', compute_type='{self.compute_type}', "
            f"beam_size='{self.beam_size}', vad_filter='{self.vad_filter}', task='{self.task}'"
        )
        logger.info("TranscriptionEngine ready.")

    def transcribe(self, audio_data: np.ndarray, language: Optional[str] = None) -> str:
        final_language = language if language is not None else self.language

        segments, _ = self.model.transcribe(
            audio_data,
            language=final_language,
            task=self.task,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
        )

        return (
            " ".join([segment.text for segment in segments])
            .strip()
            .replace("...", "")
            .replace("..", "")
            .strip()
        )
