"""Attempt to log in.

Expected: Both show the same message "Invalid username or password."
Source: "Wrong password: "Invalid username or password.""
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_attempt_log(a):
    cl = a.client()
    _, t1, _ = cl.login('nobody', 'whatever-123')
    _, t2, _ = cl.login('owner', 'whatever-123')
    assert 'Invalid username or password.' in t1 and 'Invalid username or password.' in t2
