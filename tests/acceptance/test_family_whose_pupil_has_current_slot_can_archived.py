"""A family whose pupil has a current slot can be archived.

Expected: archived
Source: "claims.json ambiguity a7 / repair setting s3"
Runs with the operator setting `directory.archive_family_with_active_pupils` = `allowed` (environment variable DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS).
"""

import pytest as _pytest_setting


@_pytest_setting.fixture(autouse=True)
def _operator_setting(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS', 'allowed')


import pytest
from _helpers.driver import App, has_error, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def test_family_whose_pupil_has_current_slot_can_archived(a, monkeypatch):
    monkeypatch.setenv('DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS', 'allowed')
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    f = ids["family"]
    a.owner.get(f"/directory/families/{f}"); _, t, _ = a.owner.req(f"/directory/families/{f}", {"action": "archive"})
    assert a.q('SELECT archived FROM families WHERE id=?', f)[0]['archived'] == 1
