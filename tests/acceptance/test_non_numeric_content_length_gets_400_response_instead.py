"""A non-numeric Content-Length gets a 400 response instead of an unhandled exception.

Expected: HTTP 400; the connection is not dropped without an answer
Source: the security review (SECURITY.md).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from _helpers.driver import App
from _helpers.security_helpers import raw, port_of


def test_non_numeric_content_length_rejected():
    a = App(setup=False)
    try:
        r = raw(port_of(a), b'POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n', timeout=5)
        assert r.startswith(b'HTTP/1.') and b' 400 ' in r.split(b'\r\n')[0], r[:100]
    finally:
        a.close()
