# Real-Time Captions

## IMPORTANT INFORMATION

This project was developed with the assistance of an AI Agent and is intended for personal use.

## Overview

"Real-Time Captions" generates real-time captions from system audio. It uses `faster-whisper` for efficient speech-to-text, `PyQt6` for the GUI, and `torch`/`transformers` for AI models. It runs in either a GUI or a background worker mode.

## How to Get Started

1.  **Install `uv`**: If you don't have `uv` (a fast Python package installer and manager), get it from [uv documentation](https://github.com/astral-sh/uv).
2.  **Install Dependencies**:
    ```bash
    uv sync
    ```

## Usage

### GUI (Graphical Interface)

To start the application with the user interface:
```bash
uv run real-time-captions
```
You can specify a language or model size:
```bash
uv run real-time-captions --language en --model-size base
```

### Worker (Background Process)

To run the transcription worker without the GUI (e.g., for background tasks or debugging):
```bash
uv run real-time-captions --worker
```
The worker also accepts language and model options:
```bash
uv run real-time-captions --worker --language pl --cpu
```
For all command-line options and available language codes, use `uv run real-time-captions --help`.

## Core Technologies

*   **Speech-to-Text**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (models from [Hugging Face](https://huggingface.co/Systran/faster-whisper-large-v3))
*   **User Interface**: `PyQt6`
*   **AI/ML Models**: `torch`, `transformers`
*   **Package Management**: `uv`

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.