"""Open the setup screen again (from the server computer) and try to create another owner.

Expected: Setup is not offered or is refused; no second account is created through it
Source: "Because no user exists, the system shows the setup screen."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_open_setup_screen_again_server_computer_try_create_another(a):
    cl = a.client()
    _, t, u = cl.req('/setup')
    assert not u.endswith('/setup')
    cl.req('/setup', {'school_name': 'S2', 'username': 'second', 'password': PW, 'password2': PW})
    assert a.q('SELECT COUNT(*) n FROM users')[0]['n'] == 1
