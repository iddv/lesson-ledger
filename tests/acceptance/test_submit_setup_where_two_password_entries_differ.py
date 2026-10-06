"""Submit setup where the two password entries differ.

Expected: The password field is marked with an error and no owner account is created
Source: "Weak password (see rules) or the two passwords differ: the field is marked and the error is shown."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


def test_submit_setup_where_two_password_entries_differ():
    b = App(setup=False)
    try:
        cl = b.client()
        _, t, u = cl.req('/setup', {'school_name': 'S', 'currency': 'GBP', 'timezone': 'UTC', 'username': 'own',
                                    'password': PW, 'password2': PW + 'x'})
        assert has_error(t) and u.endswith('/setup')
        assert b.q('SELECT COUNT(*) n FROM users')[0]['n'] == 0
    finally:
        b.close()
