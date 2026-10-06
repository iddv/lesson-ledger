"""Archiving a family whose pupil has a current slot is refused with the slot; a family without slots can be archived.

Expected: refused listing Tue 16:00; other family archived
Source: "claims.json ambiguity a7 / repair setting s3"
Runs with the operator setting `directory.archive_family_with_active_pupils` = `refused` (environment variable DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS).
"""

import pytest as _pytest_setting


@_pytest_setting.fixture(autouse=True)
def _operator_setting(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS', 'refused')


import pytest
from _helpers.driver import App, has_error, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def test_archiving_family_whose_pupil_has_current_slot_refused_slot(a, monkeypatch):
    monkeypatch.setenv('DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS', 'refused')
    ids = a.basic(); _, _, tid = a.term()
    a.slot(tid, 1, "16:00", ids["type"], ids["teacher"], ids["room"], [ids["pupil"]])
    f = ids["family"]
    a.owner.get(f"/directory/families/{f}"); _, t, _ = a.owner.req(f"/directory/families/{f}", {"action": "archive"})
    assert has_error(t) and 'Tue 16:00' in txt(t)
    assert a.q('SELECT archived FROM families WHERE id=?', f)[0]['archived'] == 0
    f2 = ids['family2']
    a.owner.get(f'/directory/families/{f2}'); a.owner.req(f'/directory/families/{f2}', {'action': 'archive'})
    assert a.q('SELECT archived FROM families WHERE id=?', f2)[0]['archived'] == 1
