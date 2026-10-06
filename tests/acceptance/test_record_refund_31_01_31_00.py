"""Record a refund of £31.01; then of £31.00.

Expected: The first is refused; the second is accepted and the balance returns to 0
Source: "Refund above the overpaid amount: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_record_refund_31_01_31_00(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-12-18')
    a.rec('lesson_types', name='P231', duration='30', price='21.00', max_pupils='1'); lt = a.last_id('lesson_types')
    a.skip(tid, '2026-10-26', '2026-11-08')  # leaves 13 Tuesdays
    a.skip(tid, '2026-12-14', '2026-12-18')  # leaves 12
    a.skip(tid, '2026-12-07', '2026-12-11')  # leaves 11 -> 231.00
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 23100
    a.invoice(iid, 'mark_paid', method='cash')
    a.invoice(iid, 'credit', amount='31.00', reason='missed', description='x')
    _, t, _ = a.invoice(iid, 'refund', amount='31.01', date='2026-09-01', method='cash'); assert has_error(t)
    _, t, _ = a.invoice(iid, 'refund', amount='31.00', date='2026-09-01', method='cash')
    assert a.q("SELECT COUNT(*) n FROM entries WHERE kind='refund'")[0]['n'] == 1
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '£0.00' in t and 'paid' in t
