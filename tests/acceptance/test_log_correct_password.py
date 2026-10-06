"""Log in with the correct password.

Expected: Login succeeds
Source: "After 5 failures the account is locked for 15 minutes (default)."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_log_correct_password(a):
    cl = a.client()
    for _ in range(4):
        cl.login('owner', 'wrong-password')
    _, t, u = cl.login('owner')
    assert u.endswith('/')
