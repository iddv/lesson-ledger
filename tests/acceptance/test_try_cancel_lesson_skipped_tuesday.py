"""Try to cancel the lesson on that skipped Tuesday.

Expected: There is no such occurrence to act on; nothing is recorded
Source: "The date is a skipped date or outside the slot's range: no such occurrence exists."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_try_cancel_lesson_skipped_tuesday(a):
    ids = a.basic(); _, _, tid = a.term(); a.skip(tid, '2026-10-27', label='Inset')
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); sid = a.last_id('slots')
    _, t, _ = a.occ(tid, sid, '2026-10-27', 'cancel')
    assert has_error(t)
    assert a.q('SELECT COUNT(*) n FROM occurrence_status')[0]['n'] == 0
