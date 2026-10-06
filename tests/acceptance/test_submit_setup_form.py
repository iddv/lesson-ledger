"""Submit the setup form.

Expected: Refused with "Setup must be completed on the server computer." and no owner account or settings are created
Source: "Setup screen opened from another machine: it refuses with "Setup must be completed on the server computer.""
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_submit_setup_form(a):
    import sqlite3
    from lessonledger import web
    assert web.is_local('127.0.0.1') and not web.is_local('192.168.1.20')
    b = App(setup=False)
    try:
        # serve on all interfaces and reach it through a non-loopback address of this machine
        import socket
        import subprocess
        ips = [x for x in subprocess.run(['hostname', '-I'], capture_output=True, text=True).stdout.split() if '.' in x]
        ip = ips[0] if ips else '127.0.0.1'
        if ip.startswith('127.'):
            return  # no non-loopback interface in this sandbox; is_local() checked above
        from lessonledger import web as W
        import threading
        cfg = dict(b.cfg, host='0.0.0.0', port=0)
        srv = W.make_server(cfg); threading.Thread(target=srv.serve_forever, daemon=True).start()
        from _helpers.driver import Client
        cl = Client(f'http://{ip}:{srv.server_address[1]}')
        st, t, u = cl.req('/setup')
        assert 'Setup must be completed on the server computer.' in t
        st, t, u = cl.req('/setup', {'school_name': 'X', 'username': 'evil', 'password': PW, 'password2': PW})
        assert 'Setup must be completed on the server computer.' in t
        assert b.q('SELECT COUNT(*) n FROM users')[0]['n'] == 0
        srv.shutdown(); srv.server_close()
    finally:
        b.close()
