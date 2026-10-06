"""Add a Tue 16:30–17:00 slot in Room 2.

Expected: Accepted (end times are exclusive)
Source: "end times are exclusive, so 16:00–16:30 and 16:30–17:00 do not conflict"
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_tue_16_30_17_00_slot_room_2(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    t, u = a.slot(tid, 1, '16:30', ids['type'], ids['teacher2'], ids['room'], [ids['pupil2']])
    assert not has_error(t) and a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 2
