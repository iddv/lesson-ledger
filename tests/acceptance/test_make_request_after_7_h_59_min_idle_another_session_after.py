"""Make a request after 7 h 59 min idle, and in another session after just over 8 h idle.

Expected: The first request works; the second requires signing in again
Source: "Sessions expire after 8 hours idle (default)."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_make_request_after_7_h_59_min_idle_another_session_after(a):
    c1 = a.client(); c1.login('owner'); c2 = a.client(); c2.login('owner')
    a.clock.advance(7 * 3600 + 59 * 60)
    assert c1.req('/terms')[2].endswith('/terms')
    a.clock.advance(61 + 60)  # c2 now idle just over 8h
    assert '/login' in c2.req('/terms')[2]
