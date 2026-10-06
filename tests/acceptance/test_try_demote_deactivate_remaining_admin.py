"""Try to demote or deactivate the remaining admin.

Expected: The first demotion succeeds; the second action is refused because that admin is now the last active one
Source: "Any admin can make other users admin, but the last active admin cannot be demoted or deactivated."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_try_demote_deactivate_remaining_admin(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'adm2', 'display_name': 'A2', 'role': 'admin', 'password': PW})
    uid2 = a.last_id('users')
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'update', 'user': uid2, 'display_name': 'A2', 'role': 'staff'})
    assert a.q('SELECT role FROM users WHERE id=?', uid2)[0]['role'] == 'staff'
    uid = a.q("SELECT id FROM users WHERE username='owner'")[0]['id']
    a.owner.get('/admin/users')
    _, t, _ = a.owner.req('/admin/users', {'action': 'update', 'user': uid, 'display_name': 'O', 'role': 'staff'})
    assert has_error(t) and a.q('SELECT role FROM users WHERE id=?', uid)[0]['role'] == 'admin'
