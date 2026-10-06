"""A payment dated the day before the issue date is refused; one on the issue date is accepted.

Expected: refused, then accepted
Source: "claims.json ambiguity a8 / repair setting s4"
Runs with the operator setting `payments.before_issue_date` = `refused` (environment variable PAYMENTS_BEFORE_ISSUE_DATE).
"""

import pytest as _pytest_setting


@_pytest_setting.fixture(autouse=True)
def _operator_setting(monkeypatch):
    monkeypatch.setenv('PAYMENTS_BEFORE_ISSUE_DATE', 'refused')


import pytest
from _helpers.driver import App, has_error, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def test_payment_dated_day_before_issue_date_refused_one_issue_date(a, monkeypatch):
    monkeypatch.setenv('PAYMENTS_BEFORE_ISSUE_DATE', 'refused')
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    a.inv_action(tid, "generate"); iid = a.invoices(tid)[0]["id"]
    a.clock.set_today("2026-09-10"); a.invoice(iid, "issue")
    _, t, _ = a.invoice(iid, "pay", amount="10.00", date="2026-09-09", method="cash")
    assert has_error(t) and a.q("SELECT COUNT(*) n FROM entries")[0]['n'] == 0
    _, t, _ = a.invoice(iid, 'pay', amount='10.00', date='2026-09-10', method='cash')
    assert not has_error(t) and a.q("SELECT COUNT(*) n FROM entries WHERE kind='payment'")[0]['n'] == 1
