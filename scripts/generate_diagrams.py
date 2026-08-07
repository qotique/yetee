"""Regenerates PlantUML class-diagrams from src via pyreverse.

Usage:
    uv run python scripts/generate_diagrams.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "docs" / "diagrams" / "generated"

EXPORTED_FILES = ("classes_yetee.puml", "packages_yetee.puml")


def _module_names() -> list[str]:
    names: list[str] = []
    for entry in sorted(SRC.iterdir(), key=lambda p: p.name):
        if entry.name == "__pycache__" or entry.name.startswith("."):
            continue
        if entry.is_dir() and (entry / "__init__.py").exists():
            names.append(entry.name)
        elif entry.suffix == ".py" and entry.name != "__init__.py":
            names.append(entry.stem)
    return names


def _pyreverse_bin() -> str:
    candidate = ROOT / ".venv" / "bin" / "pyreverse"
    return str(candidate) if candidate.exists() else "pyreverse"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        print(f"src/ not found: {SRC}")
        return 1

    modules = _module_names()
    if not modules:
        print("No modules found in src/")
        return 1

    env = dict(os.environ, PYTHONPATH=str(SRC), PYTHONUNBUFFERED="1")
    cmd = [_pyreverse_bin(), *modules, "-o", "puml", "-p", "yetee"]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, env=env)

    if result.returncode != 0:
        print(f"pyreverse exited with code {result.returncode}")
        return result.returncode

    moved = False
    for name in EXPORTED_FILES:
        produced = ROOT / name
        target = OUT / name
        if produced.exists():
            target.write_bytes(produced.read_bytes())
            produced.unlink()
            print(f"moved {name} -> {target}")
            moved = True
        else:
            print(f"WARNING: pyreverse did not produce {name}")
    if not moved:
        print("No diagrams were generated.")
        return 1
    print(f"Generated into: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())