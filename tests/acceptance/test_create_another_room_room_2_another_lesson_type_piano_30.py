"""Create another room "Room 2" and another lesson type "Piano 30".

Expected: Both are refused
Source: "Duplicate room or lesson type name: refused."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_create_another_room_room_2_another_lesson_type_piano_30(a):
    a.rec('rooms', name='Room 2'); rid = a.last_id('rooms')
    a.rec('lesson_types', name='Piano 30', duration='30', price='21', max_pupils='1')
    a.owner.get(f'/directory/rooms/{rid}'); a.owner.req(f'/directory/rooms/{rid}', {'action': 'archive'})
    t, _ = a.rec('rooms', name='Room 2'); assert has_error(t)
    t, _ = a.rec('lesson_types', name='Piano 30', duration='30', price='21', max_pupils='1'); assert has_error(t)
    assert a.q('SELECT COUNT(*) n FROM rooms')[0]['n'] == 1 and a.q('SELECT COUNT(*) n FROM lesson_types')[0]['n'] == 1
