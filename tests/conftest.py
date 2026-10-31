"""Shared pytest runtime isolation for persistent agent side effects.

Production paths remain unchanged. Runtime audit and snapshot writes that use
the default destinations are redirected into one disposable directory per
pytest process. Tests that explicitly configure their own paths keep control.
"""

import os
import shutil
import tempfile

_RUNTIME_DIR = tempfile.mkdtemp(prefix="cyberlab-agent-pytest-")
os.environ["CYBERLAB_TEST_RUNTIME_DIR"] = _RUNTIME_DIR


def pytest_sessionfinish(session, exitstatus):
    """Remove only the temporary runtime directory created by this conftest."""
    shutil.rmtree(_RUNTIME_DIR, ignore_errors=True)
    if os.environ.get("CYBERLAB_TEST_RUNTIME_DIR") == _RUNTIME_DIR:
        os.environ.pop("CYBERLAB_TEST_RUNTIME_DIR", None)
