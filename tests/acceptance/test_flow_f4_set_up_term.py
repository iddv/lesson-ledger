"""Flow F4: Set up a term.

Flow: F4 in SCOPE.md.
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


def test_F4(a):
    ids = a.basic(); _, _, old = a.term("Summer 2026", "2026-04-13", "2026-07-17")
    a.slot(old, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    a.slot(old, 3, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil2"]])
    _, _, tid = a.term(); a.skip(tid, "2026-10-26", "2026-10-30")
    a.slot(tid, 3, "16:00", ids["type"], ids["teacher2"], ids["room"], [ids["pupil"]])
    _, t, _ = a.owner.get(f"/terms/{tid}")
    nums = [int(x) for x in re.findall(r">(\d+)<", re.search(r"Teaching days per weekday.*?</tr><tr>(.*?)</tr>", t, re.S).group(1))]
    assert nums == [14, 14, 14, 14, 14, 14, 14]
    _, t, _ = a.owner.req(f"/terms/{tid}", {"action": "copy", "from": old})
    assert "Copied 1 slot" in t and "1 slot(s) were not copied" in t and "Room 2 is booked" in t
