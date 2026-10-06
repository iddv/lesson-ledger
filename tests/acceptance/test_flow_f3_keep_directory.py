"""Flow F3: Keep the directory.

Flow: F3 in SCOPE.md.
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


def test_F3(a):
    ids = a.basic(); _, _, tid = a.term()
    for kind, name in [("teachers", "Mr Jones"), ("rooms", "Room 2"), ("lesson_types", "Piano 30"), ("families", "Smith Family"), ("pupils", "Anna Smith")]:
        _, t, _ = a.owner.get(f"/directory/{kind}?q={name.split()[0]}")
        assert name in t, kind
    _, t, _ = a.owner.get(f"/directory/rooms/{ids['room2']}"); v = re.search(r"name=\"version\" value=\"(\d+)\"", t).group(1)
    a.owner.req(f"/directory/rooms/{ids['room2']}", {"action": "save", "version": v, "name": "Studio B"})
    assert "Studio B" in a.owner.get("/directory/rooms")[1]
    a.owner.get(f"/directory/rooms/{ids['room2']}"); a.owner.req(f"/directory/rooms/{ids['room2']}", {"action": "archive"})
    assert "Studio B" not in a.owner.get("/directory/rooms")[1] and "Studio B" in a.owner.get("/directory/rooms?archived=1")[1]
    a.owner.get(f"/directory/rooms/{ids['room2']}"); a.owner.req(f"/directory/rooms/{ids['room2']}", {"action": "restore"})
    assert "Studio B" in a.owner.get("/directory/rooms")[1]
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    a.owner.get(f"/directory/teachers/{ids['teacher']}")
    _, t, _ = a.owner.req(f"/directory/teachers/{ids['teacher']}", {"action": "archive"})
    assert "Tue 16:00" in t and a.q("SELECT archived FROM teachers WHERE id=?", ids["teacher"])[0]["archived"] == 0
    _, t, _ = a.owner.get(f"/families/{ids['family']}"); assert "Anna Smith" in t and "Piano 30" in t
