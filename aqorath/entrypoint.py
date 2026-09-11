"""Installed-product console entry point.

This adapter contains no accounting, HTTP or persistence rules. It prepares
the local product storage and delegates serving to the existing canonical
localhost launcher.
"""

from .local_server import run_local_surface
from .product_bootstrap import bootstrap_local_product


def main():
    bootstrap_local_product()
    return run_local_surface()


__all__ = ["main"]
