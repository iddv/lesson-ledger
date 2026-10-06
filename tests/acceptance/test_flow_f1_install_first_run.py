"""Flow F1: Install and first run.

Flow: F1 in SCOPE.md.
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


def test_F1():
    b = App(setup=False)
    try:
        cl = b.client()
        assert cl.req("/")[2].endswith("/setup")
        _, t, u = cl.req("/setup", {"school_name": "S", "address": "A", "currency": "GBP", "timezone": "UTC",
                                    "username": "owner", "password": PW, "password2": PW})
        assert u.endswith("/")
        for link in ["/directory/families", "/terms", "/timetable", "/invoices", "/payments", "/reports", "/admin"]:
            assert f"href=\"{link}\"" in t
            assert cl.req(link)[0] == 200
        assert "run.sh demo" in t
        st = cl.req("/admin/settings")[1]
        for k in ["billing.pupil_absence", "payments.overpayment", "invoices.void_permission", "timetable.copy_pupils",
                  "timetable.end_within_hours", "invoices.number_year", "directory.archive_family_with_active_pupils", "payments.before_issue_date"]:
            assert k in st, k
        env = dict(os.environ, LL_DATA_DIR=b.data_dir, LL_CONFIG="/nonexistent")
        r = subprocess.run([sys.executable, "-m", "lessonledger", "demo"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and "admin" in r.stdout
        assert b.q("SELECT COUNT(*) n FROM families")[0]["n"] == 40
        r = subprocess.run([sys.executable, "-m", "lessonledger", "demo"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode != 0 and b.q("SELECT COUNT(*) n FROM families")[0]["n"] == 40
    finally:
        b.close()
