"""Demote that admin to staff, or deactivate them (including the admin acting on themself).

Expected: Both are refused and the admin stays active and admin
Source: "the last active admin cannot be demoted or deactivated."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_demote_admin_staff_deactivate_them_including_admin_acting(a):
    uid = a.q("SELECT id FROM users WHERE username='owner'")[0]['id']
    a.owner.get('/admin/users')
    _, t, _ = a.owner.req('/admin/users', {'action': 'update', 'user': uid, 'display_name': 'Owner', 'role': 'staff'})
    assert has_error(t)
    a.owner.get('/admin/users')
    _, t, _ = a.owner.req('/admin/users', {'action': 'deactivate', 'user': uid})
    assert has_error(t)
    u = a.q('SELECT * FROM users WHERE id=?', uid)[0]
    assert u['role'] == 'admin' and u['active'] == 1
