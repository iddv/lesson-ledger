"""Save without choosing a family.

Expected: Refused with a field error; nothing is saved
Source: "every pupil belongs to exactly one family."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_without_choosing_family(a):
    t, _ = a.rec('pupils', name='Orphan', family_id='')
    assert has_error(t) and a.q('SELECT COUNT(*) n FROM pupils')[0]['n'] == 0
