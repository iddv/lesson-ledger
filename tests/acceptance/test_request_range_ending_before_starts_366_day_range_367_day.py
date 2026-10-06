"""Request a range ending before it starts, a 366-day range, and a 367-day range.

Expected: Backwards and 367-day ranges are refused; 366 days is accepted
Source: "The date range ends before it starts, or is longer than 366 days: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_request_range_ending_before_starts_366_day_range_367_day(a):
    _, t, _ = a.owner.get('/payments?start=2026-05-01&end=2026-04-01'); assert has_error(t)
    _, t, _ = a.owner.get('/payments?start=2025-09-01&end=2026-08-31'); assert not has_error(t)   # 365 days
    _, t, _ = a.owner.get('/payments?start=2025-09-01&end=2026-09-01'); assert not has_error(t)   # 366 days
    _, t, _ = a.owner.get('/payments?start=2025-08-31&end=2026-09-01'); assert has_error(t)       # 367 days
