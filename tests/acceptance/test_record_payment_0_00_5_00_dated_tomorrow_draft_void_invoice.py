"""Record a payment of £0.00, of −£5.00, dated tomorrow, and on a draft or void invoice.

Expected: Each is refused and the balance is unchanged
Source: "Amount of zero or less, or a date in the future: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_record_payment_0_00_5_00_dated_tomorrow_draft_void_invoice(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-12-18')
    a.rec('lesson_types', name='P231', duration='30', price='21.00', max_pupils='1'); lt = a.last_id('lesson_types')
    a.skip(tid, '2026-10-26', '2026-11-08')  # leaves 13 Tuesdays
    a.skip(tid, '2026-12-14', '2026-12-18')  # leaves 12
    a.skip(tid, '2026-12-07', '2026-12-11')  # leaves 11 -> 231.00
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 23100
    for amt, dte in [('0.00', '2026-09-01'), ('-5.00', '2026-09-01'), ('10.00', '2026-09-02')]:
        _, t, _ = a.invoice(iid, 'pay', amount=amt, date=dte, method='cash'); assert has_error(t), amt
    a.invoice(iid, 'void', reason='x')
    _, t, _ = a.invoice(iid, 'pay', amount='10.00', date='2026-09-01', method='cash'); assert has_error(t)
    assert a.q("SELECT COUNT(*) n FROM entries")[0]['n'] == 0
