"""Check its due date; check overdue status on the due date and on the next day with balance still above 0.

Expected: Due date is issue date + 14 days; not overdue on the due date; overdue the day after
Source: "Due date: issue date + 14 days (default). An invoice is overdue if its balance is above 0 after the due date."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_check_due_date_check_overdue_status_due_date_next_day(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']; a.invoice(iid, 'issue')
    assert a.invoices(tid)[0]['due_date'] == '2026-09-15'
    a.clock.set_today('2026-09-15'); _, t, _ = a.owner.get(f'/invoices?term={tid}'); assert 'st-overdue' not in t.split('</style>')[-1]
    a.clock.set_today('2026-09-16'); _, t, _ = a.owner.get(f'/invoices?term={tid}'); assert 'st-overdue' in t.split('</style>')[-1]
