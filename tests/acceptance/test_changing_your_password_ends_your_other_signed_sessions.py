"""Changing your password ends your other signed-in sessions.

Expected: a second session opened before the password change is sent to the login page afterwards
Source: the security review (SECURITY.md).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from _helpers.driver import App, PW


def test_password_change_ends_other_sessions():
    a = App()
    try:
        c1 = a.client(); c1.login('owner')
        c2 = a.client(); c2.login('owner')
        assert '/login' not in c2.get('/')[2]
        c1.get('/password')
        new = 'AnotherPassw0rd!'
        s, t, url = c1.req('/password', {'old': PW, 'password': new, 'password2': new})
        assert 'Password' in url or 'msg=' in url, (s, url)
        assert '/login' in c2.get('/')[2], 'old session still works after password change'
    finally:
        a.close()
