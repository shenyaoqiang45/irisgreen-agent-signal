import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("example", ["basic-projection", "image-projection"])
def test_examples_run_in_simulation(example, tmp_path):
    done = subprocess.run(
        [sys.executable, str(ROOT / "examples" / example / "main.py"),
         "--simulate", "--data-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=180, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.rstrip().endswith("done: the light is off")
