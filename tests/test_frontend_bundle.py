import subprocess
import sys


def test_release_bundle_is_current():
    subprocess.run(
        [sys.executable, "scripts/build_frontend_bundle.py", "--check"],
        check=True,
    )
