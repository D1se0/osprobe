"""Ejecutable ``python -m osprobe``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
