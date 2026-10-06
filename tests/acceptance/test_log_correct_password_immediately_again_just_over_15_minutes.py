"""Log in with the correct password immediately, and again just over 15 minutes later.

Expected: The immediate attempt is refused because the account is locked; the attempt after 15 minutes succeeds
Source: "After 5 failures the account is locked for 15 minutes (default)."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_log_correct_password_immediately_again_just_over_15_minutes(a):
    cl = a.client()
    for _ in range(5):
        cl.login('owner', 'wrong-password')
    _, t, u = cl.login('owner')
    assert '/login' in u and 'locked' in t
    a.clock.advance(15 * 60 + 5)
    _, t, u = cl.login('owner')
    assert u.endswith('/')
