"""Add a slot with the same teacher and time on Wednesday; and another with the same teacher and time on Tuesday but in a different term.

Expected: Both are accepted
Source: "two slots in the same term conflict when all of these hold"
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_slot_same_teacher_time_wednesday_another_same_teacher(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    t, u = a.slot(tid, 2, '16:00', ids['type'], ids['teacher'], ids['room2'], [ids['pupil2']]); assert not has_error(t)
    t, u = a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room2'], [ids['pupil2']])
    assert 'Mr Jones is teaching' in txt(t) and a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 2
