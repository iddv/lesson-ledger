"""Flow F6: Cancel or restore a single lesson.

Flow: F6 in SCOPE.md.
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


def test_F6(a):
    ids, tid = setup_inv(a); sid = a.q("SELECT MIN(id) m FROM slots")[0]["m"]
    a.inv_action(tid, "generate"); iid = a.invoices(tid)[0]["id"]
    assert "14 lessons" in txt(a.owner.get(f"/invoices/{iid}")[1])
    a.occ(tid, sid, "2026-09-15", "cancel", reason="Teacher ill")
    _, t, _ = a.owner.get(f"/lessons?term={tid}&date_from=2026-09-15&date_to=2026-09-15"); assert "Teacher ill" in t
    a.inv_action(tid, "regenerate"); assert "13 lessons" in txt(a.owner.get(f"/invoices/{iid}")[1])
    a.occ(tid, sid, "2026-09-15", "restore"); a.inv_action(tid, "regenerate")
    assert "14 lessons" in txt(a.owner.get(f"/invoices/{iid}")[1])
