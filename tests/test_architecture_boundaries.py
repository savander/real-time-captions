import ast
from pathlib import Path


def test_portable_core_does_not_import_platform_or_heavy_runtime_modules() -> None:
    forbidden = {"PyQt6", "torch", "transformers", "faster_whisper", "pyaudiowpatch"}
    core_files = [
        path
        for path in Path("src/real_time_captions").rglob("*.py")
        if "backends" not in path.parts
    ]

    imported: set[str] = set()
    for path in core_files:
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
