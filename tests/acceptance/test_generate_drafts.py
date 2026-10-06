"""Generate drafts.

Expected: One line per pupil, each 10 × £15.00 = £150.00, on each pupil's own family draft
Source: "The price is per pupil per lesson."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_generate_drafts(a):
    ids = a.basic(); _, _, tid = a.term('Short', '2026-09-07', '2026-11-13')
    a.rec('lesson_types', name='Group', duration='60', price='15.00', max_pupils='8'); gt = a.last_id('lesson_types')
    a.rec('pupils', name='Cara Smith', family_id=str(ids['family'])); p3 = a.last_id('pupils')
    a.slot(tid, 1, '10:00', gt, ids['teacher'], ids['room'], [ids['pupil'], ids['pupil2'], p3])
    a.inv_action(tid, 'generate')
    inv = a.invoices(tid); assert len(inv) == 2
    lines = a.q('SELECT * FROM invoice_lines')
    assert len(lines) == 3 and all(l['amount'] == 15000 for l in lines)
    tot = {i['family_id']: sum(l['amount'] for l in lines if l['invoice_id'] == i['id']) for i in inv}
    assert tot[ids['family']] == 30000 and tot[ids['family2']] == 15000
