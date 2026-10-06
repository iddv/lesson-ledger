"""Add an overlapping-time slot in Room 2 on Tue dated 21 Oct to term end; then another dated 20 Oct to term end.

Expected: The first is accepted (date ranges don't overlap); the second is refused (both include 20 Oct)
Source: "their date ranges overlap."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_overlapping_time_slot_room_2_tue_dated_21_oct_term_end(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']], end_date='2026-10-20')
    t, u = a.slot(tid, 1, '16:00', ids['type'], ids['teacher2'], ids['room'], [ids['pupil2']], start_date='2026-10-21')
    assert not has_error(t)
    t, u = a.slot(tid, 1, '16:00', ids['type'], ids['teacher2'], ids['room'], [ids['pupil2']], start_date='2026-10-20', end_date='2026-10-20')
    assert 'Room 2 is booked' in txt(t) and a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 2
