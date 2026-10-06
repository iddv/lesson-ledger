"""Flow F2: Manage staff accounts.

Flow: F2 in SCOPE.md.
"""

import re, os, sys, subprocess, pytest
from _helpers.driver import App, has_error, PW, txt, ROOT


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def setup_inv(a):
    ids = a.basic(); _, _, tid = a.term()
    a.skip(tid, "2026-10-26", "2026-10-30")
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    a.slot(tid, 2, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil2"]])
    return ids, tid


def test_F2(a):
    a.owner.get("/admin/users")
    a.owner.req("/admin/users", {"action": "add", "username": "bob", "display_name": "Bob", "role": "staff", "password": PW})
    cl = a.client(); assert cl.login("bob")[2].endswith("/password")
    cl.req("/password", {"old": PW, "password": "new-pass-123", "password2": "new-pass-123"})
    assert cl.req("/terms")[2].endswith("/terms")
    x = a.client()
    for _ in range(5):
        x.login("bob", "bad-password-1")
    _, t, u = x.login("bob", "new-pass-123"); assert "locked" in t
    uid = a.q("SELECT id FROM users WHERE username=\"owner\"")[0]["id"]
    a.owner.get("/admin/users")
    _, t, _ = a.owner.req("/admin/users", {"action": "update", "user": uid, "display_name": "O", "role": "staff"})
    assert has_error(t) and a.q("SELECT role FROM users WHERE id=?", uid)[0]["role"] == "admin"
