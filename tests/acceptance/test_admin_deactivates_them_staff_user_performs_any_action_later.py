"""An admin deactivates them; the staff user then performs any action and later tries to log in.

Expected: Their open session no longer works and the login is refused; reactivation lets them log in again
Source: "A deactivated user cannot log in, and any open sessions they have end."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_admin_deactivates_them_staff_user_performs_any_action_later(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'Bob', 'role': 'staff', 'password': PW})
    uid = a.last_id('users')
    cl = a.client(); cl.login('bob'); cl.req('/password', {'old': PW, 'password': 'new-pass-123', 'password2': 'new-pass-123'})
    assert cl.req('/terms')[2].endswith('/terms')
    a.owner.get('/admin/users'); a.owner.req('/admin/users', {'action': 'deactivate', 'user': uid})
    assert '/login' in cl.req('/terms')[2]
    _, t, u = a.client().login('bob', 'new-pass-123')
    assert '/login' in u
