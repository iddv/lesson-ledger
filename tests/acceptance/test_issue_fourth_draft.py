"""Issue a fourth draft.

Expected: The first three got consecutive numbers; the voided one keeps its number; the fourth gets the next number, with none reused or skipped
Source: "They are sequential with no gaps among issued invoices, are assigned at issue, are never reused, and void invoices keep their number."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_issue_fourth_draft(a):
    ids = a.basic(); _, _, tid = a.term()
    fams = []
    for i in range(4):
        a.rec('families', name=f'F{i}'); f = a.last_id('families')
        a.rec('pupils', name=f'Kid{i}', family_id=str(f)); p = a.last_id('pupils')
        a.slot(tid, 0, f'{10 + i}:00', ids['type'], ids['teacher'], ids['room'], [p])
    a.inv_action(tid, 'generate'); inv = a.invoices(tid); assert len(inv) == 4
    for i in inv[:3]:
        a.invoice(i['id'], 'issue')
    a.invoice(inv[1]['id'], 'void', reason='x')
    a.invoice(inv[3]['id'], 'issue')
    nums = [i['number'] for i in a.invoices(tid)]
    assert nums == ['2026-0001', '2026-0002', '2026-0003', '2026-0004']
    assert a.invoices(tid)[1]['status'] == 'void'
