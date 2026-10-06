"""Click "Generate drafts" again.

Expected: Existing drafts and the issued invoice are untouched, no family gets a second invoice, and the fully cancelled family gets none
Source: "Generating twice: existing drafts and issued invoices are kept, and only families without a non-void invoice get new drafts."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_click_generate_drafts_again(a):
    ids = a.basic(); _, _, tid = a.term()
    a.rec('families', name='Gone Family'); f3 = a.last_id('families')
    a.rec('pupils', name='Gus', family_id=str(f3)); p3 = a.last_id('pupils')
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.slot(tid, 2, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil2']])
    a.slot(tid, 3, '16:00', '1', ids['teacher'], ids['room'], [p3], start_date='2026-09-09', end_date='2026-09-09'); s3 = a.last_id('slots')
    a.occ(tid, s3, '2026-09-09', 'cancel')
    a.inv_action(tid, 'generate')
    inv = a.invoices(tid); assert len(inv) == 2
    a.invoice(inv[0]['id'], 'issue')
    a.inv_action(tid, 'generate')
    inv2 = a.invoices(tid)
    assert [i['id'] for i in inv2] == [i['id'] for i in inv] and not any(i['family_id'] == f3 for i in inv2)
