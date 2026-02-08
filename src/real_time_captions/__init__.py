import argparse
import logging

from rich.traceback import install as enable_rich_traceback

from .logging_config import setup_logging

logger = logging.getLogger(__name__)


LANGUAGE_CODES = [
    "af",
    "am",
    "ar",
    "as",
    "az",
    "ba",
    "be",
    "bg",
    "bn",
    "bo",
    "br",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fo",
    "fr",
    "gl",
    "gu",
    "ha",
    "haw",
    "he",
    "hi",
    "hr",
    "ht",
    "hu",
    "hy",
    "id",
    "is",
    "it",
    "ja",
    "jw",
    "ka",
    "kk",
    "km",
    "kn",
    "ko",
    "la",
    "lb",
    "ln",
    "lo",
    "lt",
    "lv",
    "mg",
    "mi",
    "mk",
    "ml",
    "mn",
    "mr",
    "ms",
    "mt",
    "my",
    "ne",
    "nl",
    "nn",
    "no",
    "oc",
    "pa",
    "pl",
    "ps",
    "pt",
    "ro",
    "ru",
    "sa",
    "sd",
    "si",
    "sk",
    "sl",
    "sn",
    "so",
    "sq",
    "sr",
    "su",
    "sv",
    "sw",
    "ta",
    "te",
    "tg",
    "th",
    "tk",
    "tl",
    "tr",
    "tt",
    "uk",
    "ur",
    "uz",
    "vi",
    "yi",
    "yo",
    "zh",
    "yue",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-time auto captions")
    parser.add_argument(
        "--language",
        "-l",
        type=str,
        default=None,
        choices=LANGUAGE_CODES,
        metavar="CODE",
        help="Set the language for transcription.",
    )
    parser.add_argument(
        "--model-size",
        "-m",
        type=str,
        default=None,
        help="Override automatic model size detection (e.g., tiny, base, small, medium, large-v3)",
    )
    parser.add_argument(
        "--cpu", action="store_true", help="Force CPU usage even if a GPU is available."
    )
    parser.add_argument(
        "--max-cpu-ram-gb",
        "-r",
        type=int,
        default=None,
        help="Restrict perceived RAM in GB for CPU model selection (e.g., 8, 16).",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)

    args, _ = parser.parse_known_args()

    setup_logging(is_worker_process=args.worker)
    enable_rich_traceback(max_frames=1, extra_lines=1, show_locals=False)

    if args.worker:
        from .worker import run_worker_logic

        run_worker_logic(
            args.language,
            model_size_override=args.model_size,
            force_cpu=args.cpu,
            max_cpu_ram_gb=args.max_cpu_ram_gb,
        )
    else:
        from .gui import run_gui

        run_gui(
            args.language,
            model_size_override=args.model_size,
            force_cpu=args.cpu,
            max_cpu_ram_gb=args.max_cpu_ram_gb,
        )
