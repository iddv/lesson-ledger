"""Flow F8: Record payments, refunds and corrections.

Flow: F8 in SCOPE.md.
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


def test_F8(a):
    ids, tid = setup_inv(a)
    a.inv_action(tid, "generate"); iid = a.invoices(tid)[0]["id"]; a.invoice(iid, "issue")
    _, t, _ = a.invoice(iid, "pay", amount="294.01", date="2026-09-01", method="cash"); assert has_error(t)
    a.invoice(iid, "mark_paid", method="card")
    _, t, _ = a.owner.get(f"/invoices/{iid}"); assert "pill st-paid" in t
    eid = a.q("SELECT id FROM entries WHERE kind=\"payment\"")[0]["id"]
    a.invoice(iid, "reverse", entry=eid, reason="bounced")
    _, t, _ = a.owner.get(f"/invoices/{iid}"); assert "£294.00" in t and "pill st-paid" not in t
    assert a.q("SELECT COUNT(*) n FROM entries")[0]["n"] == 2
