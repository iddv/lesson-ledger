"""An admin voids it; then reverses the payment and voids again.

Expected: The first void is refused; after reversal the void succeeds, keeping the invoice, its lines and number
Source: "Voiding an invoice that has payments: refused until the payments are reversed or refunded."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_admin_voids_reverses_payment_voids_again(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-12-18')
    a.rec('lesson_types', name='P231', duration='30', price='21.00', max_pupils='1'); lt = a.last_id('lesson_types')
    a.skip(tid, '2026-10-26', '2026-11-08')  # leaves 13 Tuesdays
    a.skip(tid, '2026-12-14', '2026-12-18')  # leaves 12
    a.skip(tid, '2026-12-07', '2026-12-11')  # leaves 11 -> 231.00
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 23100
    a.invoice(iid, 'pay', amount='50.00', date='2026-09-01', method='cash')
    _, t, _ = a.invoice(iid, 'void', reason='x'); assert has_error(t) and a.invoices(tid)[0]['status'] == 'issued'
    eid = a.q("SELECT id FROM entries WHERE kind='payment'")[0]['id']
    a.invoice(iid, 'reverse', entry=eid, reason='mistake')
    a.invoice(iid, 'void', reason='x'); assert a.invoices(tid)[0]['status'] == 'void'
