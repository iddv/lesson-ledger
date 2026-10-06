"""Add a slot of that type with 9 pupils; then with 8.

Expected: 9 is refused; 8 is accepted
Source: "More pupils than the type allows: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_slot_type_9_pupils_8(a):
    ids = a.basic(); _, _, tid = a.term()
    a.rec('lesson_types', name='Group', duration='60', price='10', max_pupils='8'); gt = a.last_id('lesson_types')
    pids = []
    for i in range(9):
        a.rec('pupils', name=f'P{i}', family_id=str(ids['family'])); pids.append(a.last_id('pupils'))
    t, u = a.slot(tid, 3, '10:00', gt, ids['teacher'], ids['room'], pids); assert has_error(t)
    t, u = a.slot(tid, 3, '10:00', gt, ids['teacher'], ids['room'], pids[:8]); assert not has_error(t)
    assert a.q('SELECT COUNT(*) n FROM slot_pupils')[0]['n'] == 8
