"""Try to reach the service from another machine on the LAN.

Expected: It is not reachable; it listens only on 127.0.0.1:8080
Source: "The service listens on 127.0.0.1:8080. LAN access requires setting the listen address explicitly."
"""

import re, pytest
from _helpers.driver import App, has_error, PW, txt


def test_try_reach_service_another_machine_lan():
    from lessonledger import db
    import tempfile, os
    cfg = db.load_config({'LL_DATA_DIR': tempfile.mkdtemp(), 'LL_CONFIG': '/nonexistent'})
    assert cfg['host'] == '127.0.0.1' and int(cfg['port']) == 8080
