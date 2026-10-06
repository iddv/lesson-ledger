"""Start the service.

Expected: It exits with a message naming the port and the setting that changes it
Source: "Port already in use: the service exits with a message naming the port and the setting that changes it."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


def test_start_service():
    import socket, subprocess, sys, tempfile, os
    from _helpers.driver import ROOT
    s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1); port = s.getsockname()[1]
    try:
        env = dict(os.environ, LL_DATA_DIR=tempfile.mkdtemp(), LL_PORT=str(port), LL_CONFIG='/nonexistent')
        r = subprocess.run([sys.executable, '-m', 'lessonledger', 'serve'], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=20)
        out = r.stdout + r.stderr
        assert r.returncode != 0 and str(port) in out and 'LL_PORT' in out
    finally:
        s.close()
