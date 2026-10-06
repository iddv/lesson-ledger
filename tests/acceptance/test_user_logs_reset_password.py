"""The user logs in with the reset password.

Expected: They are forced to change it before doing anything else
Source: "reset a password (again must-change)"
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_user_logs_reset_password(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'Bob', 'role': 'staff', 'password': PW})
    uid = a.last_id('users')
    cl = a.client(); cl.login('bob'); cl.req('/password', {'old': PW, 'password': 'new-pass-123', 'password2': 'new-pass-123'})
    a.owner.get('/admin/users'); a.owner.req('/admin/users', {'action': 'reset', 'user': uid, 'password': 'reset-pass-99'})
    cl2 = a.client(); _, t, u = cl2.login('bob', 'reset-pass-99')
    assert u.endswith('/password')
    _, t, u = cl2.req('/terms'); assert '/password' in u
