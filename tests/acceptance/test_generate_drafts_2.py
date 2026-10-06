"""Generate drafts.

Expected: A new draft is created for that family; storage never holds two non-void invoices for one family and term
Source: "at most one non-void invoice per family per term, enforced in storage."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_generate_drafts_2(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue'); a.invoice(iid, 'void', reason='x')
    a.inv_action(tid, 'generate')
    inv = a.invoices(tid); assert len(inv) == 2 and inv[1]['status'] == 'draft'
    a.inv_action(tid, 'generate'); assert len(a.invoices(tid)) == 2
