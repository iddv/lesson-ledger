"""Run the demo data command.

Expected: Refused, and the data is exactly as before
Source: "Demo command run on a database that has data: it refuses and changes nothing."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


@pytest.fixture
def a():
    app = App(); app.clock.set_today('2026-09-01')
    yield app
    app.close()


def test_run_demo_data_command(a):
    import subprocess, sys, os
    from _helpers.driver import ROOT
    a.rec('teachers', name='Mr Jones')
    before = a.q('SELECT COUNT(*) n FROM teachers')[0]['n']
    env = dict(os.environ, LL_DATA_DIR=a.data_dir, LL_CONFIG='/nonexistent')
    r = subprocess.run([sys.executable, '-m', 'lessonledger', 'demo'], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert a.q('SELECT COUNT(*) n FROM teachers')[0]['n'] == before
    assert a.q('SELECT COUNT(*) n FROM families')[0]['n'] == 0
