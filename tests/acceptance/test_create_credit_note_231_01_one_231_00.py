"""Create a credit note for £231.01; then one for £231.00.

Expected: The first is refused; the second is accepted with a reason
Source: "A credit note larger than the remaining invoice total: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_create_credit_note_231_01_one_231_00(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-12-18')
    a.rec('lesson_types', name='P231', duration='30', price='21.00', max_pupils='1'); lt = a.last_id('lesson_types')
    a.skip(tid, '2026-10-26', '2026-11-08')  # leaves 13 Tuesdays
    a.skip(tid, '2026-12-14', '2026-12-18')  # leaves 12
    a.skip(tid, '2026-12-07', '2026-12-11')  # leaves 11 -> 231.00
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 23100
    _, t, _ = a.invoice(iid, 'credit', amount='231.01', reason='too much', description='x')
    assert has_error(t) and a.q('SELECT COUNT(*) n FROM credit_notes')[0]['n'] == 0
    _, t, _ = a.invoice(iid, 'credit', amount='231.00', reason='all', description='x')
    assert a.q('SELECT COUNT(*) n FROM credit_notes')[0]['n'] == 1
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert 'paid' in txt(t)
