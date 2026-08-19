import ast
import tomllib
from pathlib import Path


def package_files() -> list[Path]:
    return list(Path("src/real_time_captions").rglob("*.py"))


def test_boundary_scan_includes_current_backend_protocol_modules() -> None:
    scanned = package_files()

    assert Path("src/real_time_captions/backends/__init__.py") in scanned
    assert Path("src/real_time_captions/backends/protocols.py") in scanned


def test_portable_core_does_not_import_platform_or_heavy_runtime_modules() -> None:
    forbidden = {"PyQt6", "torch", "transformers", "faster_whisper", "pyaudiowpatch"}

    imported: set[str] = set()
    for path in package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(forbidden)
    architecture = Path("docs/Architecture.md")
    assert architecture.exists()
    documentation = architecture.read_text(encoding="utf-8")
    assert all(
        contract in documentation
        for contract in ("AudioSource", "AsrBackend", "TranslationBackend")
    )


def test_architecture_documents_reviewed_runtime_and_state_boundaries() -> None:
    documentation = Path("docs/Architecture.md").read_text(encoding="utf-8")

    assert "Translation failure occurs after source state has been applied" in documentation
    assert "missing settings file returns defaults without warnings" in documentation
    assert all(
        field in documentation
        for field in (
            "DiagnosticsSnapshot",
            "first_caption_p50",
            "first_caption_p95",
            "commit_p50",
            "commit_p95",
            "coalesced_windows",
            "worker_restarts",
            "AppSettings",
            "target",
            "view_mode",
            "profile",
            "locked_language",
        )
    )


def test_manifest_does_not_declare_unused_platformdirs() -> None:
    manifest = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = manifest["project"]["dependencies"]

    assert all(not dependency.startswith("platformdirs") for dependency in dependencies)
