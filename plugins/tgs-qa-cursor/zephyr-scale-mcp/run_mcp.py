"""Запуск MCP через .venv плагина (Cursor часто вызывает system python из PATH)."""
from __future__ import annotations

import os
import sys


def _root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _venv_python(root: str) -> str | None:
    if sys.platform == "win32":
        candidate = os.path.join(root, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(root, ".venv", "bin", "python")
    return candidate if os.path.isfile(candidate) else None


def main() -> None:
    root = _root()
    py = _venv_python(root) or sys.executable
    env = os.environ.copy()
    src = os.path.join(root, "src")
    prev = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not prev else f"{src}{os.pathsep}{prev}"
    os.chdir(root)
    argv = [py, "-m", "zephyr_scale_mcp"]
    os.execve(py, argv, env)


if __name__ == "__main__":
    main()
