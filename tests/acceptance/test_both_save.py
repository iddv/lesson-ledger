"""Both save.

Expected: Exactly one is saved; the other is refused with the clash
Source: "Slot saves run the conflict check and the save in one transaction, so two staff booking the same room at once cannot both succeed."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_both_save(a):
    import threading
    ids = a.basic(); _, _, tid = a.term()
    c2 = a.client(); c2.login('owner')
    for cl in (a.owner, c2):
        cl.get(f'/slots/new?term={tid}')
    res = []
    def go(cl, teacher, pupil):
        res.append(cl.req(f'/slots/new?term={tid}', {'term': tid, 'weekday': 1, 'start': '16:00', 'lesson_type_id': ids['type'],
            'teacher_id': teacher, 'room_id': ids['room'], 'pupils': [str(pupil)], 'start_date': '', 'end_date': ''}))
    th = [threading.Thread(target=go, args=(a.owner, ids['teacher'], ids['pupil'])),
          threading.Thread(target=go, args=(c2, ids['teacher2'], ids['pupil2']))]
    [x.start() for x in th]; [x.join() for x in th]
    assert a.q('SELECT COUNT(*) n FROM slots')[0]['n'] == 1
    assert sum('Room 2 is booked' in r[1] for r in res) == 1
