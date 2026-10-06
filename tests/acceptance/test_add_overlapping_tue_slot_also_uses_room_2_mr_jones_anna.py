"""Add an overlapping Tue slot that also uses Room 2, Mr Jones and Anna.

Expected: Refused with three separate clash lines: room, teacher and pupil
Source: "Each clash is reported separately."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_overlapping_tue_slot_also_uses_room_2_mr_jones_anna(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    t, u = a.slot(tid, 1, '16:15', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    tx = txt(t)
    assert 'Room 2 is booked' in tx and 'Mr Jones is teaching' in tx and 'Anna Smith already has' in tx
    assert a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 1
