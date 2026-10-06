"""Autumn 2026 invoice issued in Jan 2027 numbered with 2027.

Expected: 2026 issue -> 2026-0001; Jan 2027 issue -> 2027-0001
Source: "claims.json ambiguity a2 / repair setting s2"
Runs with the operator setting `invoices.number_year` = `issue_date` (environment variable INVOICES_NUMBER_YEAR).
"""

import pytest as _pytest_setting


@_pytest_setting.fixture(autouse=True)
def _operator_setting(monkeypatch):
    monkeypatch.setenv('INVOICES_NUMBER_YEAR', 'issue_date')


import pytest
from _helpers.driver import App, has_error, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def test_autumn_2026_invoice_issued_jan_2027_numbered_2027(a, monkeypatch):
    monkeypatch.setenv('INVOICES_NUMBER_YEAR', 'issue_date')
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    a.slot(tid, 2, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil2"]])
    a.inv_action(tid, "generate"); i1, i2 = [i["id"] for i in a.invoices(tid)]
    a.clock.set_today('2026-12-20'); a.invoice(i1, 'issue')
    a.clock.set_today('2027-01-05'); a.invoice(i2, 'issue')
    assert [i['number'] for i in a.invoices(tid)] == ['2026-0001', '2027-0001']
