"""Try to manage users, change operator settings, download a backup or view the audit log.

Expected: Each is refused and nothing changes
Source: "Staff can do everything except user management, settings, backup/restore, viewing the audit log, and voiding when the setting is admin-only."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_try_manage_users_change_operator_settings_download_backup(a):
    a.owner.get('/admin/users')
    a.owner.req('/admin/users', {'action': 'add', 'username': 'bob', 'display_name': 'Bob', 'role': 'staff', 'password': PW})
    cl = a.client(); cl.login('bob'); cl.req('/password', {'old': PW, 'password': 'new-pass-123', 'password2': 'new-pass-123'})
    for p in ['/admin/users', '/admin/settings', '/admin/backup/download', '/admin/audit']:
        s, t, u = cl.req(p)
        assert s in (403, 404) or 'not allowed' in t.lower() or 'admin' in t.lower() and 'only' in t.lower(), p
        assert 'SQLite' not in t
    cl.req('/admin/users', {'action': 'add', 'username': 'eve', 'display_name': 'E', 'role': 'admin', 'password': PW})
    cl.req('/admin/settings', {'payments.overpayment': 'allow_credit'})
    assert a.q("SELECT COUNT(*) n FROM users WHERE username='eve'")[0]['n'] == 0
    from lessonledger import core
    assert a.q("SELECT COUNT(*) n FROM settings WHERE key='payments.overpayment' AND value='allow_credit'")[0]['n'] == 0
