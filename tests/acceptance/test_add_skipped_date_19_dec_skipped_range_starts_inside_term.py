"""Add a skipped date of 19 Dec, and a skipped range that starts inside the term and ends after it.

Expected: Both are refused
Source: "A skipped date outside the term: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_add_skipped_date_19_dec_skipped_range_starts_inside_term(a):
    _, _, tid = a.term()
    _, t, _ = a.skip(tid, '2026-12-19'); assert has_error(t)
    _, t, _ = a.skip(tid, '2026-12-15', '2026-12-22'); assert has_error(t)
    assert a.q('SELECT COUNT(*) n FROM skipped')[0]['n'] == 0
