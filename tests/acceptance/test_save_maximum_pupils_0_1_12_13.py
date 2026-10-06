"""Save with maximum pupils 0, 1, 12 and 13.

Expected: 0 and 13 are refused; 1 and 12 are accepted; leaving it blank gives 1
Source: "Maximum pupils is 1–12, default 1 (default)."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_save_maximum_pupils_0_1_12_13(a):
    for i, (mp, ok) in enumerate([('0', False), ('1', True), ('12', True), ('13', False)]):
        n0 = a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n']
        a.rec('lesson_types', name=f'T{i}', duration='30', price='10.00', max_pupils=mp)
        assert (a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n'] == n0 + 1) == ok, mp
    a.rec('lesson_types', name='Blank', duration='30', price='10.00', max_pupils='')
    assert a.q("SELECT max_pupils FROM lesson_types WHERE name='Blank'")[0]['max_pupils'] == 1
