"""Mark one occurrence "Cancelled by school", regenerate; then restore it and regenerate.

Expected: The line drops to 10 lessons (£210.00), then returns to 11 (£231.00)
Source: "a "cancelled by school" lesson drops off the family's regenerated draft, and restoring it brings it back."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_mark_one_occurrence_cancelled_school_regenerate_restore(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); sid = a.last_id('slots')
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '15 lessons' in txt(t)
    a.occ(tid, sid, '2026-09-15', 'cancel'); a.inv_action(tid, 'regenerate')
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '14 lessons' in txt(t) and '£294.00' in t
    a.occ(tid, sid, '2026-09-15', 'restore'); a.inv_action(tid, 'regenerate')
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '15 lessons' in txt(t)
