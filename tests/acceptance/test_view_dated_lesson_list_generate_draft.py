"""View its dated lesson list and generate a draft.

Expected: Only Tuesdays within both the slot's range and the term, excluding skipped dates, are listed and counted
Source: "a slot's occurrences are its weekday's dates within both the term and the slot's own date range, minus the term's skipped dates."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_view_dated_lesson_list_generate_draft(a):
    ids = a.basic(); _, _, tid = a.term()
    a.skip(tid, '2026-10-26', '2026-10-30')
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']], start_date='2026-10-13')
    _, t, _ = a.owner.get(f'/lessons?term={tid}&date_from=2026-09-01&date_to=2026-12-31')
    dates = sorted(set(re.findall(r'2026-1[0-2]-\d\d', txt(t))))
    assert '2026-10-27' not in dates and '2026-10-06' not in dates and '2026-10-13' in dates
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    _, t, _ = a.owner.get(f'/invoices/{iid}')
    # Tuesdays 13 Oct .. 15 Dec = 10, minus half-term 27 Oct = 9
    assert '9 lessons' in txt(t)
