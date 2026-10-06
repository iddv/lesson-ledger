"""Add a Tue 16:25–16:55 slot in Room 2 with a different teacher and pupil.

Expected: Refused with a line naming the room, the day and time, the lesson type, teacher and pupil of the existing slot; nothing is saved
Source: "Conflict: the slot is refused with one line per clash, e.g. "Room 2 is booked Tue 16:00–16:30 by Piano 30 (Mr Jones, Anna Smith)." Nothing is saved."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_tue_16_25_16_55_slot_room_2_different_teacher_pupil(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    t, u = a.slot(tid, 1, '16:25', ids['type'], ids['teacher2'], ids['room'], [ids['pupil2']])
    assert 'Room 2 is booked Tue 16:00–16:30 by Piano 30 (Mr Jones, Anna Smith).' in t
    assert a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 1
