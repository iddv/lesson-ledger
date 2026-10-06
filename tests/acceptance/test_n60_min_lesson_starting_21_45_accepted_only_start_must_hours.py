"""A 60-min lesson starting 21:45 is accepted when only the start must be in hours.

Expected: 21:45 accepted; 06:55 still refused
Source: "claims.json ambiguity a1 / repair setting s1"
Runs with the operator setting `timetable.end_within_hours` = `start_only` (environment variable TIMETABLE_END_WITHIN_HOURS).
"""

import pytest as _pytest_setting


@_pytest_setting.fixture(autouse=True)
def _operator_setting(monkeypatch):
    monkeypatch.setenv('TIMETABLE_END_WITHIN_HOURS', 'start_only')


import pytest
from _helpers.driver import App, has_error, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today("2026-09-01")
    yield app
    app.close()


def test_n60_min_lesson_starting_21_45_accepted_only_start_must_hours(a, monkeypatch):
    monkeypatch.setenv("TIMETABLE_END_WITHIN_HOURS", "start_only")
    ids = a.basic(); _, _, tid = a.term()
    a.rec("lesson_types", name="L60", duration="60", price="10", max_pupils="1"); lt = a.last_id("lesson_types")
    t, _ = a.slot(tid, 4, "21:45", lt, ids["teacher"], ids["room"], [ids["pupil"]]); assert not has_error(t)
    t, _ = a.slot(tid, 4, "06:55", lt, ids["teacher"], ids["room"], [ids["pupil"]]); assert has_error(t)
    assert a.q("SELECT COUNT(*) n FROM slots")[0]["n"] == 1
