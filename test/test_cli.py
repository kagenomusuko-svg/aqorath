"""Tests for CLI commands in main.py"""
import subprocess
import sys
from pathlib import Path


def test_cli_help():
    """Test that CLI help works."""
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "SistemaContable" in result.stdout
    assert "fetch-xsds" in result.stdout
    assert "import-timbrado" in result.stdout
    assert "generate-cfdi" in result.stdout


def test_fetch_xsds_help():
    """Test that fetch-xsds help works."""
    result = subprocess.run(
        [sys.executable, "main.py", "fetch-xsds", "--help"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "--url" in result.stdout
    assert "--verify" in result.stdout
    assert "--shafile" in result.stdout


def test_import_timbrado_help():
    """Test that import-timbrado help works."""
    result = subprocess.run(
        [sys.executable, "main.py", "import-timbrado", "--help"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "--id" in result.stdout
    assert "--file" in result.stdout
