"""Regenerate the pinned requirements files from the .in files.

Preferred: uv (universal resolution, so the lock installs on Linux/py3.12 and
on developer machines alike). Fallback: pip-tools inside python:3.12-slim.
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMD = "npm run deps:compile"
PAIRS = [
    ("requirements.in", "requirements.txt"),
    ("requirements-dev.in", "requirements-dev.txt"),
]


def _uv_commands(uv: str) -> list[list[str]]:
    return [
        [
            uv, "pip", "compile", src,
            "--universal",
            "--python-version", "3.12",
            "--strip-extras",
            "--custom-compile-command", CMD,
            "-o", out,
        ]
        for src, out in PAIRS
    ]  # fmt: skip


def _docker_command() -> list[str]:
    inner = (
        "pip install -q pip-tools && "
        "pip-compile -q --strip-extras -o requirements.txt requirements.in && "
        "pip-compile -q --strip-extras -o requirements-dev.txt requirements-dev.in"
    )
    return [
        "docker", "run", "--rm",
        "-v", f"{ROOT}:/app", "-w", "/app",
        "python:3.12-slim", "sh", "-c", inner,
    ]  # fmt: skip


def main() -> None:
    uv = shutil.which("uv")
    commands = _uv_commands(uv) if uv else [_docker_command()]
    for cmd in commands:
        subprocess.run(cmd, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
