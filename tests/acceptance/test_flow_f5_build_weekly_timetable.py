"""Flow F5: Build the weekly timetable.

Flow: F5 in SCOPE.md.
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


def test_F5(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    t, _ = a.slot(tid, 1, "16:15", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    tx = txt(t); assert "Room 2 is booked" in tx and "Mr Jones is teaching" in tx and "Anna Smith already has" in tx
    t, _ = a.slot(tid, 1, "16:30", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]]); assert not has_error(t)
    _, t, _ = a.owner.get(f"/timetable/print?term={tid}&view=room&room_id={ids['room']}")
    tx = txt(t); assert "Room 2" in tx and "16:00–16:30" in tx and "16:30–17:00" in tx and "Tue" in tx
