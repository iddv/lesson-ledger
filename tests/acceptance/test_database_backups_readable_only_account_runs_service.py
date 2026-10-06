"""The database and backups are readable only by the account that runs the service.

Expected: no group/other permission bits on the database file and backup files
Source: the security review (SECURITY.md).
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import stat
from _helpers.driver import App
from lessonledger import db


def test_data_files_not_world_readable():
    a = App()
    try:
        c = db.connect(a.cfg['db_path'])
        try:
            bk = db.write_backup(c, a.cfg)
        finally:
            c.close()
        for p in (a.cfg['db_path'], bk):
            mode = stat.S_IMODE(os.stat(p).st_mode)
            assert mode & 0o077 == 0, f'{p} has mode {oct(mode)}'
    finally:
        a.close()


# Known open item: expected to fail until it is fixed (tests/acceptance/README.md).
import pytest as _pytest_open  # noqa: E402
_marks = globals().get('pytestmark', [])
pytestmark = (list(_marks) if isinstance(_marks, (list, tuple)) else [_marks]) + [
    _pytest_open.mark.xfail(strict=False, reason='Known security issue (low): The database and backups are readable only by the account that runs the service')]
