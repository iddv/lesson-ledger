"""Save with a price of 0, a negative price, a non-numeric price, and a price with more than two decimal places.

Expected: Each is refused with a field-level error and nothing is saved
Source: "Missing or invalid field (e.g. price not a positive amount, duration outside 15–120 min): a field-level error and nothing is saved."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_price_0_negative_price_non_numeric_price_price_more(a):
    for i, p in enumerate(['0', '-5.00', 'abc', '10.001']):
        t, u = a.rec('lesson_types', name=f'T{i}', duration='30', price=p, max_pupils='1')
        assert has_error(t), p
    assert a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n'] == 0
