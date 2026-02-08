# Real-Time Captions

> [!CAUTION]
> **Experimental / Personal Use Only** 
>
> I built the architecture and mapped out the logic for this project myself, but I let an AI handle the actual coding. It’s a "vibe coded" experiment meant for my own personal use, so it definitely isn't production-ready. Use it at your own risk!

## Overview

"Real-Time Captions" generates real-time captions from system audio. It uses `faster-whisper` for efficient speech-to-text, `PyQt6` for the GUI, and `torch`/`transformers` for AI models.

Crucially, a worker process is always spawned. In GUI mode, this worker communicates via Inter-Process Communication (IPC) to send captions to the UI. When run in standalone worker mode (`--worker`), the worker directly prints the captions to the console.

## How to Get Started

1.  **Install `uv`**: If you don't have `uv` (a fast Python package installer and manager), get it from [uv documentation](https://github.com/astral-sh/uv).
2.  **Install Dependencies**:
    ```bash
    uv sync
    ```

## Usage

### GUI (Graphical Interface)

To start the application with the graphical user interface:
```bash
uv run real-time-captions
```
You can specify a language or model size:
```bash
uv run real-time-captions --language en --model-size base
```

### Worker (Background Process)

To run the transcription worker process without the GUI (e.g., for background tasks or debugging):
```bash
uv run real-time-captions --worker
```
The worker also accepts language and model options:
```bash
uv run real-time-captions --worker --language pl --cpu
```
For all command-line options and available language codes, use `uv run real-time-captions --help`.

### Recommendations for Lower-End Systems

For systems with limited resources (e.g., older CPUs, less RAM, no dedicated GPU), consider the following options to optimize performance:

*   **Use smaller models**: The `tiny` or `base` models are less resource-intensive than `small`, `medium`, or `large`.
    ```bash
    uv run real-time-captions --model-size tiny
    ```
*   **Force CPU usage**: If you have a low-end or integrated GPU, forcing the application to use the CPU might sometimes be more stable, though generally slower.
    ```bash
    uv run real-time-captions --cpu
    ```
*   **Limit CPU RAM**: If you have a lot of RAM but want to simulate a lower-memory environment for model selection on CPU, you can restrict the perceived RAM. This can help the system pick smaller, more appropriate models for your actual usage.
    ```bash
    uv run real-time-captions --max-cpu-ram-gb 8
    ```

## Core Technologies

*   **Speech-to-Text**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (models from [Hugging Face](https://huggingface.co/Systran/faster-whisper-large-v3))
*   **User Interface**: [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
*   **AI/ML Models**: [torch](https://pytorch.org/), [transformers](https://huggingface.co/docs/transformers/)
*   **Package Management**: [uv](https://astral.sh/uv)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
