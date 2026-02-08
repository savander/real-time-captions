import logging
import platform
import subprocess
from typing import Any, Dict, Optional

import psutil

logger = logging.getLogger(__name__)


def _get_nvidia_gpu_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {"vendor": "NVIDIA", "available": False}
    try:
        import torch

        if torch.cuda.is_available():
            info["available"] = True
            info["device_count"] = torch.cuda.device_count()
            devices = []
            for i in range(info["device_count"]):
                props = torch.cuda.get_device_properties(i)
                devices.append(
                    {
                        "name": props.name,
                        "major": props.major,
                        "minor": props.minor,
                        "total_memory_gb": round(props.total_memory / (1024**3), 2),
                        "is_rtx": "RTX" in props.name or props.major >= 7,
                    }
                )
            info["devices"] = devices
    except Exception as e:
        logger.debug(f"NVIDIA GPU detection failed: {e}")
    return info


def _get_amd_gpu_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {"vendor": "AMD", "available": False}
    system = platform.system()

    if system == "Linux":
        try:
            result = subprocess.run(
                ["lspci", "-v"], capture_output=True, text=True, check=True
            )
            if "Radeon" in result.stdout or "AMD/ATI" in result.stdout:
                info["available"] = True
                info["devices"] = [{"name": "AMD Radeon (via lspci)"}]
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.debug(f"AMD GPU detection (Linux) failed: {e}")
    elif system == "Windows":
        try:
            result = subprocess.run(
                ["wmic", "path", "Win32_VideoController", "get", "Name"],
                capture_output=True,
                text=True,
                check=True,
            )
            if "AMD" in result.stdout or "Radeon" in result.stdout:
                info["available"] = True
                names = [
                    line.strip()
                    for line in result.stdout.splitlines()
                    if "AMD" in line or "Radeon" in line
                ]
                info["devices"] = [{"name": name} for name in names]
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.debug(f"AMD GPU detection (Windows) failed: {e}")
    return info


def get_hardware_info() -> Dict[str, Any]:
    hardware_info: Dict[str, Any] = {
        "system": platform.system(),
        "processor": platform.processor(),
        "gpus": {"nvidia": {}, "amd": {}},
    }

    nvidia_info = _get_nvidia_gpu_info()
    if nvidia_info["available"]:
        hardware_info["gpus"]["nvidia"] = nvidia_info
    else:
        hardware_info["gpus"]["nvidia"]["available"] = False

    amd_info = _get_amd_gpu_info()
    if amd_info["available"]:
        hardware_info["gpus"]["amd"] = amd_info
    else:
        hardware_info["gpus"]["amd"]["available"] = False

    return hardware_info


def get_optimal_device_settings(hardware_info: Dict[str, Any]) -> Dict[str, Any]:
    settings: Dict[str, Any] = {
        "device": "cpu",
        "compute_type": "int8",
        "beam_size": 1,
        "vad_filter": True,
        "initial_prompt": "Clean transcript. No hesitation markers.",
    }

    if hardware_info["gpus"]["nvidia"].get("available"):
        nvidia_gpus = hardware_info["gpus"]["nvidia"].get("devices", [])
        settings["device"] = "cuda"
        if any(gpu.get("is_rtx") or gpu.get("major", 0) >= 7 for gpu in nvidia_gpus):
            settings["compute_type"] = "float16"
            settings["beam_size"] = 5
        else:
            settings["compute_type"] = "float16"
            settings["beam_size"] = 3
        logger.info(
            f"NVIDIA GPU detected. Using device: '{settings['device']}' with compute_type: '{settings['compute_type']}'"
        )
    elif hardware_info["gpus"]["amd"].get("available"):
        settings["device"] = "cpu"
        settings["compute_type"] = "int8"
        settings["beam_size"] = 1
        logger.warning(
            "AMD GPU detected, but native acceleration is not supported by faster-whisper. "
            "Falling back to CPU for transcription. Consider community ROCm solutions for better performance."
        )
    else:
        logger.info("No supported GPU detected. Using CPU for transcription.")

    return settings


def get_optimal_model_size(
    hardware_info: Dict[str, Any],
    force_cpu: bool = False,
    max_cpu_ram_gb: Optional[int] = None,
) -> str:
    recommended_model = "base"

    if not force_cpu and hardware_info["gpus"]["nvidia"].get("available"):
        nvidia_gpus = hardware_info["gpus"]["nvidia"].get("devices", [])
        if nvidia_gpus:
            total_vram_gb = nvidia_gpus[0].get("total_memory_gb", 0)

            if total_vram_gb >= 10:
                recommended_model = "large-v3"
            elif total_vram_gb >= 5:
                recommended_model = "medium"
            elif total_vram_gb >= 2:
                recommended_model = "small"
            else:
                recommended_model = "tiny"
            logger.info(
                f"NVIDIA GPU detected with {total_vram_gb} GB VRAM. Recommended model: '{recommended_model}'"
            )

    if force_cpu or not hardware_info["gpus"]["nvidia"].get("available"):
        try:
            if max_cpu_ram_gb is not None:
                total_ram_gb = max_cpu_ram_gb
                logger.info(
                    f"Using restricted CPU RAM for model selection: {total_ram_gb} GB."
                )
            else:
                total_ram_bytes = psutil.virtual_memory().total
                total_ram_gb = round(total_ram_bytes / (1024**3), 2)

            if total_ram_gb >= 16:
                recommended_model = "medium"
            elif total_ram_gb >= 8:
                recommended_model = "small"
            else:
                recommended_model = "base"

            if force_cpu:
                logger.info(
                    f"CPU usage forced. System RAM: {total_ram_gb} GB. Recommended model: '{recommended_model}' for CPU execution."
                )
            else:
                logger.info(
                    f"No NVIDIA GPU. System RAM: {total_ram_gb} GB. Recommended model: '{recommended_model}' for CPU execution."
                )
        except Exception as e:
            logger.warning(
                f"Could not determine system RAM for optimal model selection: {e}. Defaulting to '{recommended_model}'."
            )

    return recommended_model