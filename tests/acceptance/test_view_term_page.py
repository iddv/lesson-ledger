"""View the term page.

Expected: Each weekday's teaching-day count equals its dates in the term minus skipped dates (Mondays reduced by 2, Tue–Fri by 1)
Source: "The term page shows each teaching week and, for every weekday, the number of teaching days."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_view_term_page(a):
    _, _, tid = a.term()
    a.skip(tid, '2026-10-26', '2026-10-30'); a.skip(tid, '2026-09-14', label='Bank holiday')
    _, t, _ = a.owner.get(f'/terms/{tid}')
    m = re.search(r'Teaching days per weekday.*?</tr><tr>(.*?)</tr>', t, re.S)
    nums = [int(x) for x in re.findall(r'>(\d+)<', m.group(1))]
    # term Mon 7 Sep - Fri 18 Dec 2026: 15 Mon..Fri, 14 Sat/Sun
    assert nums == [13, 14, 14, 14, 14, 14, 14]
