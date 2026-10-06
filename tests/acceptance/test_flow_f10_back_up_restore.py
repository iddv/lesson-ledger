"""Flow F10: Back up and restore.

Flow: F10 in SCOPE.md.
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


def test_F10(a):
    import urllib.request, tempfile
    ids, tid = setup_inv(a)
    a.inv_action(tid, "generate"); a.inv_action(tid, "issue_all"); i1 = a.invoices(tid)[0]["id"]
    a.invoice(i1, "pay", amount="50.00", date="2026-09-01", method="cash")
    r = a.owner.op.open(a.base + "/admin/backup/download"); data = r.read()
    f = os.path.join(a.tmp, "b.db"); open(f, "wb").write(data)
    b = App(setup=False); b.close()
    env = dict(os.environ, LL_DATA_DIR=b.data_dir, LL_CONFIG="/nonexistent")
    r = subprocess.run([sys.executable, "-m", "lessonledger", "restore", f], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    for tb in ["families", "pupils", "slots", "invoices", "invoice_lines", "entries", "users", "settings"]:
        assert b.q(f"SELECT * FROM {tb} ORDER BY 1") == a.q(f"SELECT * FROM {tb} ORDER BY 1"), tb
    bad = os.path.join(a.tmp, "bad.db"); open(bad, "wb").write(b"not a database" * 100)
    r = subprocess.run([sys.executable, "-m", "lessonledger", "restore", bad], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert b.q("SELECT COUNT(*) n FROM invoices")[0]["n"] == 2
