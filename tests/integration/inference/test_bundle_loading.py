from __future__ import annotations

import subprocess
import sys


def test_api_safe_runtime_import_does_not_import_anomalib() -> None:
    code = (
        "import sys; import inspection_platform.inference.runtime; "
        "assert 'anomalib' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
