"""Hard delete the pupil.

Expected: Refused; a pupil never used in a slot or invoice can be hard deleted
Source: "Hard delete is only possible for records never used in a slot or invoice."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_hard_delete_pupil(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.owner.get(f'/directory/pupils/{ids["pupil"]}')
    _, t, _ = a.owner.req(f'/directory/pupils/{ids["pupil"]}', {'action': 'delete'})
    assert a.q('SELECT COUNT(*) n FROM pupils WHERE id=?', ids['pupil'])[0]['n'] == 1
    a.owner.get(f'/directory/pupils/{ids["pupil2"]}')
    a.owner.req(f'/directory/pupils/{ids["pupil2"]}', {'action': 'delete'})
    assert a.q('SELECT COUNT(*) n FROM pupils WHERE id=?', ids['pupil2'])[0]['n'] == 0
