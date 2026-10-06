"""Submit setup with a 9-character password, then again with a 10-character password typed identically twice.

Expected: The 9-character password is refused with a field error and nothing is created; the 10-character one creates the owner, signs them in and shows the empty dashboard
Source: "Passwords: at least 10 characters (default)."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


def test_submit_setup_9_character_password_again_10_character():
    b = App(setup=False)
    try:
        cl = b.client()
        f = {'school_name': 'S', 'currency': 'GBP', 'timezone': 'UTC', 'username': 'own'}
        _, t, u = cl.req('/setup', dict(f, password='a' * 9, password2='a' * 9))
        assert 'at least 10' in t and b.q('SELECT COUNT(*) n FROM users')[0]['n'] == 0
        _, t, u = cl.req('/setup', dict(f, password='a' * 10, password2='a' * 10))
        assert u.endswith('/') and b.q('SELECT COUNT(*) n FROM users')[0]['n'] == 1
    finally:
        b.close()
