import importlib.util
import os
import sys
from typing import List


def setup_cuda_runtime() -> None:
    if sys.platform != "win32":
        return

    packages_to_check: List[str] = ["nvidia.cublas", "nvidia.cudnn", "torch"]
    additional_paths: List[str] = []

    for pkg in packages_to_check:
        try:
            spec = importlib.util.find_spec(pkg)
            if spec and spec.submodule_search_locations:
                pkg_path: str = spec.submodule_search_locations[0]

                potential_dirs = [
                    os.path.join(pkg_path, "bin"),
                    os.path.join(pkg_path, "lib"),
                ]

                for d in potential_dirs:
                    if os.path.exists(d):
                        os.add_dll_directory(d)
                        additional_paths.append(d)
        except (ModuleNotFoundError, ImportError):
            continue

    if additional_paths:
        os.environ["PATH"] = (
            os.pathsep.join(additional_paths) + os.pathsep + os.environ["PATH"]
        )
