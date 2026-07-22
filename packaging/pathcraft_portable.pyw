"""PyInstaller entry point for the portable Windows application."""

from pathcraft.windows_app import main


if __name__ == "__main__":
    raise SystemExit(main())
