"""The staff user logs in with the temporary password and tries to open any page other than changing the password.

Expected: They must set a new password first; after doing so they can use the system and the temporary password no longer works
Source: "On first login the user must set a new password."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_staff_user_logs_temporary_password_tries_open_any_page_other(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'Bob', 'role': 'staff', 'password': PW})
    cl = a.client()
    _, t, u = cl.login('bob')
    assert u.endswith('/password')
    _, t, u = cl.req('/directory/families')
    assert '/password' in u
    _, t, u = cl.req('/password', {'old': PW, 'password': 'new-pass-123', 'password2': 'new-pass-123'})
    _, t, u = cl.req('/directory/families')
    assert u.endswith('/directory/families')
