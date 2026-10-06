"""Archive the teacher, then try to pick them for a new slot, then view the old term's timetable and invoices, then restore them.

Expected: Archive succeeds; they cannot be chosen for a new slot; they still appear on past history and invoices; after restore they can be chosen again
Source: "It disappears from pickers but stays on history and invoices, and can be restored."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_archive_teacher_try_pick_them_new_slot_view_old_term(a):
    ids = a.basic(); _, _, old = a.term('Spring 2026', '2026-01-05', '2026-03-27')
    a.slot(old, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(old, 'generate')
    _, _, tid = a.term()
    a.owner.get(f'/directory/teachers/{ids["teacher"]}')
    a.owner.req(f'/directory/teachers/{ids["teacher"]}', {'action': 'archive'})
    assert a.q('SELECT archived FROM teachers WHERE id=?', ids['teacher'])[0]['archived'] == 1
    t, u = a.slot(tid, 2, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    assert has_error(t) and a.q('SELECT COUNT(*) n FROM slots WHERE term_id=?', tid)[0]['n'] == 0
    _, t, _ = a.owner.get(f'/timetable?term={old}'); assert 'Mr Jones' in t
    a.owner.get(f'/directory/teachers/{ids["teacher"]}')
    a.owner.req(f'/directory/teachers/{ids["teacher"]}', {'action': 'restore'})
    t, u = a.slot(tid, 2, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    assert not has_error(t)
