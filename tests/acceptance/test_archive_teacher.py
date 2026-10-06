"""Archive the teacher.

Expected: Refused, with a list of the slots to end first; the teacher stays active
Source: "Archiving a teacher, room, pupil or lesson type that has slots in the current or a future term: refused, with a list of those slots to end first."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_archive_teacher(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.owner.get(f'/directory/teachers/{ids["teacher"]}')
    _, t, _ = a.owner.req(f'/directory/teachers/{ids["teacher"]}', {'action': 'archive'})
    assert has_error(t) and 'Tue 16:00' in t
    assert a.q('SELECT archived FROM teachers WHERE id=?', ids['teacher'])[0]['archived'] == 0
