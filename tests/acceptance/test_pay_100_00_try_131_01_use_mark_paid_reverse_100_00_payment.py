"""Pay £100.00; then try £131.01; then use Mark paid; then reverse the £100.00 payment.

Expected: Status part-paid with £131.00 due; £131.01 refused; Mark paid records £131.00 and status becomes paid with balance 0; after the reversal the balance is £100.00 and status part-paid, with the original payment still listed
Source: "mark paid sets the balance to 0 and the status to paid, a reversal restores the balance, and an overpayment is refused under the default setting."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_pay_100_00_try_131_01_use_mark_paid_reverse_100_00_payment(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-12-18')
    a.rec('lesson_types', name='P231', duration='30', price='21.00', max_pupils='1'); lt = a.last_id('lesson_types')
    a.skip(tid, '2026-10-26', '2026-11-08')  # leaves 13 Tuesdays
    a.skip(tid, '2026-12-14', '2026-12-18')  # leaves 12
    a.skip(tid, '2026-12-07', '2026-12-11')  # leaves 11 -> 231.00
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 23100
    a.invoice(iid, 'pay', amount='100.00', date='2026-09-01', method='cash')
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert 'part-paid' in t and '£131.00' in t
    _, t, _ = a.invoice(iid, 'pay', amount='131.01', date='2026-09-01', method='cash'); assert has_error(t)
    a.invoice(iid, 'mark_paid', method='card')
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '>paid<' in t.replace(' st-paid', '') or 'pill st-paid' in t
    eid = a.q("SELECT id FROM entries WHERE kind='payment' ORDER BY id")[0]['id']
    a.invoice(iid, 'reverse', entry=eid, reason='bounced')
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert 'part-paid' in t and '£100.00' in t
