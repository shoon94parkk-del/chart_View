"""Basic API imports must not retain the optional HTML dataframe parser."""
import os
import subprocess
import sys
from pathlib import Path


def test_ordinary_api_import_does_not_load_pandas():
    result = subprocess.run(
        [sys.executable, '-c', 'import sys; import main; assert "pandas" not in sys.modules, "ordinary API import eagerly loaded optional pandas parser"'],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
