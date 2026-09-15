"""Smoke tests of the scripts in examples/."""

import subprocess
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_quickstart_runs(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(EXAMPLES / "quickstart.py"), str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "[AMAC] success=True" in completed.stdout
    assert completed.stdout.count("[facade] image_") == 2
    assert (tmp_path / "store-dft-dummy.json").is_file()
    assert (tmp_path / "facade" / "image_001").is_dir()


def test_usage_examples_compile():
    """The illustrative scripts need real programs: they are compiled, not run."""
    scripts = sorted((EXAMPLES / "usage").glob("*.py"))
    assert len(scripts) >= 9
    for script in scripts:
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
