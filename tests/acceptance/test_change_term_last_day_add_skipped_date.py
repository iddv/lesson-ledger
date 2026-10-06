"""Change the term's last day or add a skipped date.

Expected: Refused with "Void the term's invoices first."; after voiding all its invoices the change is allowed
Source: "Changing dates or skipped dates after invoices exist: refused with "Void the term's invoices first.""
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_change_term_last_day_add_skipped_date(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    a.invoice(iid, 'issue')
    a.owner.get(f'/terms/{tid}')
    _, t, _ = a.owner.req(f'/terms/{tid}', {'action': 'save', 'version': '1', 'name': 'Autumn 2026', 'first_day': '2026-09-07', 'last_day': '2026-12-11'})
    assert "Void the term's invoices first." in t.replace('&#x27;', "'")
    _, t, _ = a.skip(tid, '2026-10-26', '2026-10-30')
    assert "Void the term's invoices first." in t.replace('&#x27;', "'")
    a.invoice(iid, 'void', reason='mistake')
    _, t, _ = a.skip(tid, '2026-10-26', '2026-10-30')
    assert a.q('SELECT COUNT(*) n FROM skipped')[0]['n'] == 1
