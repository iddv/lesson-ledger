"""Add a Tue 16:15 slot with a different teacher and room that includes Anna.

Expected: Refused with a pupil clash line naming Anna
Source: "they share a room, a teacher or a pupil"
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_tue_16_15_slot_different_teacher_room_includes_anna(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    t, u = a.slot(tid, 1, '16:15', ids['type'], ids['teacher2'], ids['room2'], [ids['pupil']])
    tx = txt(t)
    assert 'Anna Smith already has' in tx and 'Room 2 is booked' not in tx and 'is teaching' not in tx
