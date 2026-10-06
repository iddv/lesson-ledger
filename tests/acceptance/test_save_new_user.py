"""Save the new user.

Expected: Refused with "Username already taken." and no user is created
Source: "Duplicate username: "Username already taken.""
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_new_user(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'Bob', 'role': 'staff', 'password': PW})
    uid = a.last_id('users')
    a.owner.get('/admin/users'); a.owner.req('/admin/users', {'action': 'deactivate', 'user': uid})
    a.owner.get('/admin/users')
    _, t, _ = a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'B2', 'role': 'staff', 'password': PW})
    assert 'Username already taken.' in t
    assert a.q("SELECT COUNT(*) n FROM users WHERE username='bob'")[0]['n'] == 1
