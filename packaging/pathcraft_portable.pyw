"""PyInstaller entry point for the portable Windows application."""

from pathcraft.desktop_bridge import main


if __name__ == "__main__":
    raise SystemExit(main())
