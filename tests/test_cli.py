import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_help_lists_transport_options() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "yuanbao_search_mcp", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--transport" in result.stdout
    assert "--port" in result.stdout


def test_version_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "yuanbao_search_mcp", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
