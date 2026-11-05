import subprocess
import sys

import pytest

from billing_platform.process_limits import memory_limit


def test_rejects_invalid_process_limit_without_affecting_parent():
    with pytest.raises(ValueError):
        memory_limit(0)


def test_real_child_cannot_allocate_beyond_hard_memory_limit():
    code = """
from billing_platform.process_limits import memory_limit
memory_limit(64 * 1024 * 1024)
try:
    content = bytearray(128 * 1024 * 1024)
except MemoryError:
    print('bounded')
else:
    raise SystemExit(3)
"""
    result = subprocess.run(  # noqa: S603 -- fixed test program, never caller input.
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bounded"
