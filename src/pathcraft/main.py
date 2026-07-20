"""Backward-compatible imports for the historical module path."""

from .cli import InteractiveConfig, main

__all__ = ["InteractiveConfig", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
