"""Save with the last day before the first day; save another term whose dates overlap an existing term by one day.

Expected: Both are refused; the overlap error names the clashing term
Source: "The last day is before the first day, or the term overlaps another term: refused with the clashing term named."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_last_day_before_first_day_save_another_term_whose_dates(a):
    _, _, t1 = a.term('Autumn 2026', '2026-09-07', '2026-12-18')
    t, u, _ = a.term('Bad', '2027-02-01', '2027-01-01'); assert has_error(t)
    t, u, _ = a.term('Overlap', '2026-12-18', '2027-03-01'); assert has_error(t) and 'Autumn 2026' in t
    assert a.q('SELECT COUNT(*) n FROM terms')[0]['n'] == 1
