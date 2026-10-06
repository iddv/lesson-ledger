"""After login, the next= parameter can only send the user to a page on this site.

Expected: next=/\\evil.example redirects to / (browsers treat /\\host as //host, another site)
Source: the security review (SECURITY.md).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import urllib.error, urllib.parse, urllib.request
from _helpers.driver import App, PW


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):
        return None


def test_login_next_backslash_not_offsite():
    a = App()
    try:
        op = urllib.request.build_opener(NoRedirect)
        body = urllib.parse.urlencode({'username': 'owner', 'password': PW, 'next': '/\\evil.example'}).encode()
        try:
            op.open(a.base + '/login', body)
            loc = None
        except urllib.error.HTTPError as e:
            loc = e.headers.get('Location')
        assert loc is not None
        assert '\\' not in loc and 'evil.example' not in loc, loc
    finally:
        a.close()
