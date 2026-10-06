"""Edit a different Tue slot to move it into Room 2 at 16:15.

Expected: Refused with the clash named; the edited slot keeps its old values
Source: "Every edit is re-checked."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_edit_different_tue_slot_move_into_room_2_16_15(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.slot(tid, 1, '10:00', ids['type'], ids['teacher2'], ids['room2'], [ids['pupil2']]); sid = a.last_id('slots')
    _, t, _ = a.owner.get(f'/slots/{sid}'); v = re.search(r'name="version" value="(\d+)"', t).group(1)
    _, t, _ = a.owner.req(f'/slots/{sid}', {'action': 'save', 'version': v, 'weekday': 1, 'start': '16:15',
        'lesson_type_id': ids['type'], 'teacher_id': ids['teacher2'], 'room_id': ids['room'], 'pupils': [str(ids['pupil2'])],
        'start_date': '2026-09-07', 'end_date': '2026-12-18'})
    assert 'Room 2 is booked' in txt(t)
    s = a.q('SELECT * FROM slots WHERE id=?', sid)[0]
    assert s['start_min'] == 600 and s['room_id'] == ids['room2']
