"""Close the term; then settle the remaining invoice and close again.

Expected: The first close is refused; the second succeeds
Source: "then close the term once all its invoices are paid or void."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_close_term_settle_remaining_invoice_close_again(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    a.invoice(iid, 'issue'); a.invoice(iid, 'pay', amount='10.00', date='2026-09-01', method='cash')
    a.owner.get(f'/terms/{tid}'); _, t, _ = a.owner.req(f'/terms/{tid}', {'action': 'close'})
    assert has_error(t) and a.q('SELECT closed FROM terms')[0]['closed'] == 0
    a.invoice(iid, 'mark_paid', method='cash')
    a.owner.get(f'/terms/{tid}'); a.owner.req(f'/terms/{tid}', {'action': 'close'})
    assert a.q('SELECT closed FROM terms')[0]['closed'] == 1
