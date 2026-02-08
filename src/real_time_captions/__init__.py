import logging

from rich.traceback import install as enable_rich_traceback

from .args import parse_arguments
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    args = parse_arguments()

    setup_logging(is_worker_process=args.worker)
    enable_rich_traceback(max_frames=1, extra_lines=1, show_locals=False)

    if args.worker:
        from .worker import run_worker_logic

        run_worker_logic(
            args.language,
            model_size_override=args.model_size,
            force_cpu=args.cpu,
            max_cpu_ram_gb=args.max_cpu_ram_gb,
            task=args.task,
            use_microphone=args.microphone,
        )
    else:
        from .gui import run_gui

        run_gui(
            args.language,
            model_size_override=args.model_size,
            force_cpu=args.cpu,
            max_cpu_ram_gb=args.max_cpu_ram_gb,
            task=args.task,
            use_microphone=args.microphone,
        )
