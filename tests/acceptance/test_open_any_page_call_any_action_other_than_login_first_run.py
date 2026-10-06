"""Open any page or call any action other than login (or first-run setup).

Expected: Refused / redirected to login; no data is returned or changed
Source: "Every page and action requires login."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_open_any_page_call_any_action_other_than_login_first_run(a):
    ids = a.basic()
    cl = a.client()
    for p in ['/', '/directory/families', f'/families/{ids["family"]}', '/terms', '/timetable', '/invoices',
              '/payments', '/reports', '/admin', '/admin/users', '/admin/backup/download', '/lessons']:
        _, t, u = cl.req(p)
        assert '/login' in u and 'Smith Family' not in t, p
    _, t, u = cl.req('/directory/rooms/new', {'action': 'save', 'name': 'Hacked'})
    assert a.q("SELECT COUNT(*) n FROM rooms WHERE name='Hacked'")[0]['n'] == 0
