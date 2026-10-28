"""Optional desktop entry point, keeping command-line imports Qt-free."""
from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    try:
        from .gui import main as launch
    except ImportError as exc:
        if exc.name and (exc.name == 'PySide6' or exc.name.startswith('PySide6.')):
            raise SystemExit("Install desktop support first: python -m pip install -e '.[desktop]'") from exc
        raise
    return launch(argv)
