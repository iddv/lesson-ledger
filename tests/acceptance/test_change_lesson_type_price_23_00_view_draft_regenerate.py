"""Change the lesson type price to £23.00; view the draft; then regenerate it.

Expected: Before regenerating the draft still shows £21.00; after, it uses £23.00 and the −£10.00 adjustment is kept
Source: "The price is copied onto the line, so later price changes don't alter drafts already generated until they are regenerated."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_change_lesson_type_price_23_00_view_draft_regenerate(a):
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, '16:00', ids['type'], ids['teacher'], ids['room'], [ids['pupil']])
    a.inv_action(tid, 'generate'); iid = a.invoices(tid)[0]['id']
    a.invoice(iid, 'adjust', description='Sibling discount', amount='-10.00')
    _, t, _ = a.owner.get(f'/directory/lesson_types/{ids["type"]}'); v = re.search(r'name="version" value="(\d+)"', t).group(1)
    a.owner.req(f'/directory/lesson_types/{ids["type"]}', {'action': 'save', 'version': v, 'name': 'Piano 30', 'duration': '30', 'price': '23.00', 'max_pupils': '1'})
    _, t, _ = a.owner.get(f'/invoices/{iid}'); assert '£21.00' in t and '£23.00' not in t
    a.invoice(iid, 'regenerate')
    _, t, _ = a.owner.get(f'/invoices/{iid}')
    assert '£23.00' in t and 'Sibling discount' in t
    assert sum(l['amount'] for l in a.q('SELECT amount FROM invoice_lines WHERE invoice_id=?', iid)) == 15 * 2300 - 1000
