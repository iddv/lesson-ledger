"""Save with duration 14, 15, 120 and 121 minutes.

Expected: 14 and 121 are refused with a field error and nothing is saved; 15 and 120 are accepted
Source: "Lesson types: duration 15–120 minutes."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_duration_14_15_120_121_minutes(a):
    for i, (dur, ok) in enumerate([('14', False), ('15', True), ('120', True), ('121', False)]):
        n0 = a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n']
        t, u = a.rec('lesson_types', name=f'T{i}', duration=dur, price='10.00', max_pupils='1')
        n1 = a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n']
        assert (n1 == n0 + 1) == ok, dur
        if not ok:
            assert has_error(t)
