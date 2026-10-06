"""Flow F7: Generate, review and issue term invoices.

Flow: F7 in SCOPE.md.
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


def test_F7(a):
    ids, tid = setup_inv(a)
    a.inv_action(tid, "generate"); a.inv_action(tid, "generate")
    inv = a.invoices(tid); assert len(inv) == 2 and len({i["family_id"] for i in inv}) == 2
    a.inv_action(tid, "issue_all")
    assert sorted(i["number"] for i in a.invoices(tid)) == ["2026-0001", "2026-0002"]
    iid = inv[0]["id"]
    _, t, _ = a.owner.get(f"/invoices/{iid}/print"); tx = txt(t)
    assert "Test School" in tx and "2026-0001" in tx and "2026-09-15" in tx and "Half-term" in tx and "2026-10-26" in tx
    a.invoice(iid, "credit", amount="21.00", reason="missed", description="Missed lesson")
    assert a.q("SELECT COUNT(*) n FROM credit_notes")[0]["n"] == 1
    assert "£273.00" in a.owner.get(f"/invoices/{iid}")[1]
    assert a.owner.get(f"/invoices/print?term={tid}")[0] == 200
