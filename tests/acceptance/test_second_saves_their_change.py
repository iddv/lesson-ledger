"""The second saves their change.

Expected: Refused with "This record changed since you opened it," showing the newer values; the first change is kept
Source: "Another user saved the same record first: "This record changed since you opened it," and the newer values are shown."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_second_saves_their_change(a):
    ids = a.basic(); fid = ids['family']
    c2 = a.client(); c2.login('owner')
    _, t1, _ = a.owner.get(f'/directory/families/{fid}')
    v = re.search(r'name="version" value="(\d+)"', t1).group(1)
    a.owner.req(f'/directory/families/{fid}', {'action': 'save', 'version': v, 'name': 'Smith A', 'phone': '111'})
    c2.get(f'/directory/families/{fid}')
    _, t, _ = c2.req(f'/directory/families/{fid}', {'action': 'save', 'version': v, 'name': 'Smith B', 'phone': '222'})
    assert 'This record changed since you opened it' in t and 'Smith A' in t
    assert a.q('SELECT name FROM families WHERE id=?', fid)[0]['name'] == 'Smith A'
