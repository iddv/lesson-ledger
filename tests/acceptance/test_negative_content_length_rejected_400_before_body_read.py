"""A negative Content-Length is rejected with 400 before the body is read.

Expected: the server answers 400 at once instead of reading the connection until it closes
Source: the security review (SECURITY.md).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from _helpers.driver import App
from _helpers.security_helpers import raw, port_of


def test_negative_content_length_rejected():
    a = App(setup=False)
    try:
        # the client keeps its side open; a correct server answers without waiting for EOF
        r = raw(port_of(a), b'POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\n' + b'a' * 65536, timeout=5)
        assert r.startswith(b'HTTP/1.') and b' 400 ' in r.split(b'\r\n')[0], r[:100]
    finally:
        a.close()
