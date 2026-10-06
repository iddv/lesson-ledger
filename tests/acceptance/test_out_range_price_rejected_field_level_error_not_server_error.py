"""An out-of-range price is rejected with a field-level error, not a server error.

Expected: price 99999999999999999999.00 -> 200 page with a field error on price, nothing saved
Source: ""Validation: all input is validated on the server before anything is saved." / "clear field-level messages""
"""

import pytest
from _helpers.driver import App, has_error


@pytest.fixture
def a():
    app = App()
    yield app
    app.close()


def test_out_range_price_rejected_field_level_error_not_server_error(a):
    a.owner.get('/directory/lesson_types/new')
    s, t, _ = a.owner.req('/directory/lesson_types/new', {'action': 'save', 'name': 'Huge', 'duration': '30',
                                                          'price': '99999999999999999999.00', 'max_pupils': '1'})
    assert s == 200 and has_error(t), (s, t[-300:])
    assert a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n'] == 0
