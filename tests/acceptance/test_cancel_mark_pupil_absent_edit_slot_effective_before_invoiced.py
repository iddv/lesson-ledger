"""Cancel it, mark it pupil absent, or edit its slot effective on or before the invoiced period's end.

Expected: Refused with "Issue a credit note instead."
Source: "The occurrence is on an issued invoice: refused with "Issue a credit note instead.""
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_cancel_mark_pupil_absent_edit_slot_effective_before_invoiced(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']]); sid = a.last_id('slots')
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    for act in ('cancel', 'absent'):
        _, t, _ = a.occ(tid, sid, '2026-09-15', act)
        assert 'Issue a credit note instead.' in t, act
    a.owner.get(f'/slots/{sid}'); _, t, _ = a.owner.req(f'/slots/{sid}', {'action': 'end', 'from_date': '2026-11-01'})
    assert 'Issue a credit note instead.' in t
    assert a.q('SELECT end_date FROM slots WHERE id=?', sid)[0]['end_date'] == '2026-12-18'
