"""Add a slot starting 06:55; one starting 07:00; one starting 16:03.

Expected: 06:55 is refused (outside hours); 07:00 is accepted; 16:03 is refused (not a 5-minute step)
Source: "Opening hours: 07:00–22:00 (default). Start times are on 5-minute steps."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_slot_starting_06_55_one_starting_07_00_one_starting_16(a):
    ids = a.basic(); _, _, tid = a.term()
    t, _ = a.slot(tid, 0, '06:55', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); assert has_error(t)
    t, _ = a.slot(tid, 0, '07:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); assert not has_error(t)
    t, _ = a.slot(tid, 2, '16:03', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); assert has_error(t)
    assert a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 1
