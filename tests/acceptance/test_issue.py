"""Issue it.

Expected: Refused; the draft stays a draft with no number
Source: "Issuing a draft with a total of 0 or less: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_issue(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-09-30')
    a.rec('lesson_types', name='P12', duration='30', price='12.50', max_pupils='1'); lt = a.last_id('lesson_types')
    a.slot(tid, 1, '16:00', lt, ids['teacher'], ids['room'], [ids['pupil']])  # 4 Tuesdays = 50.00
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    a.invoice(iid, 'adjust', description='Waive', amount='-50.00')
    _, t, _ = a.invoice(iid, 'issue')
    inv = a.invoices(tid)[0]
    assert has_error(t) and inv['status'] == 'draft' and inv['number'] is None
