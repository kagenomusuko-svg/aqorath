"""Tiny PyInstaller root; all product behavior remains inside aqorath."""

from aqorath.desktop_entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
