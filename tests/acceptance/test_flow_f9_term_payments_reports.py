"""Flow F9: Term and payments reports.

Flow: F9 in SCOPE.md.
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


def test_F9(a):
    ids, tid = setup_inv(a)
    a.inv_action(tid, "generate"); a.inv_action(tid, "issue_all")
    i1, i2 = [i["id"] for i in a.invoices(tid)]
    a.invoice(i1, "pay", amount="100.00", date="2026-09-01", method="cash")
    a.invoice(i2, "mark_paid", method="card")
    _, t, _ = a.owner.get(f"/reports?term={tid}&csv=1")
    tot = [l for l in t.splitlines() if l.startswith("TOTAL")][0].split(",")
    assert tot[2:] == ["588.00", "0.00", "394.00", "0.00", "194.00"]
    _, t, _ = a.owner.get("/payments?start=2026-09-01&end=2026-09-30&csv=1")
    assert "100.00" in t and "294.00" in t and "cash" in t.lower() and "card" in t.lower()
