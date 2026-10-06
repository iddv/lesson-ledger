"""Thin helpers over Lesson Ledger's real HTTP interface (in-process server on 127.0.0.1).
Clock: core.TODAY_OVERRIDE (the build's own date hook) and Clock for wall time (time.time used by
sessions/lockout; the build has no hook for it, so Clock swaps the `time` name seen by core)."""
import os as _os
# These helpers find the repository from their own location. They live in
# tests/acceptance/_helpers/; paths are computed as if they sat one level below
# the repository root.
_HERE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))), '_helpers', 'driver.py')
import datetime as dt
import http.cookiejar
import os
import re
import sqlite3
import sys
import tempfile
import threading
import types
import time as _time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_HERE)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from lessonledger import core, db, web  # noqa: E402

PW = 'correct-horse-1'


class Clock:
    def __init__(self):
        self.offset = 0.0
        fake = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith('__')})
        fake.time = lambda: _time.time() + self.offset
        self._fake = fake
        core.time = fake
        web.time = fake

    def advance(self, seconds):
        self.offset += seconds

    def set_today(self, day):
        core.TODAY_OVERRIDE = dt.date.fromisoformat(day) if isinstance(day, str) else day

    def close(self):
        core.time = _time
        web.time = _time
        core.TODAY_OVERRIDE = None


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''

    def req(self, path, data=None):
        body = None
        if data is not None:
            data = dict(data)
            data.setdefault('csrf', self.csrf)
            body = urllib.parse.urlencode(data, doseq=True).encode()
        try:
            r = self.op.open(self.base + path, body)
            status, text, url = r.status, r.read().decode('utf-8', 'replace'), r.url
        except urllib.error.HTTPError as e:
            status, text, url = e.code, e.read().decode('utf-8', 'replace'), e.url
        m = re.search(r'name="csrf" value="([^"]+)"', text)
        if m:
            self.csrf = m.group(1)
        return status, text, url

    def get(self, path):
        return self.req(path)

    def post(self, path, **data):
        if not self.csrf:
            self.req(path.split('?')[0] if 'csrf' not in data else path)
        return self.req(path, data)

    def login(self, username, pw=PW):
        self.req('/login')
        return self.req('/login', {'username': username, 'password': pw})


class App:
    def __init__(self, data_dir=None, setup=True, env=None):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = data_dir or os.path.join(self.tmp, 'd')
        e = {'LL_DATA_DIR': self.data_dir, 'LL_PORT': '0', 'LL_CONFIG': os.path.join(self.tmp, 'none')}
        e.update(env or {})
        self.cfg = db.load_config(e)
        db.open_db(self.cfg).close()
        self.srv = web.make_server(self.cfg)
        self.base = f'http://127.0.0.1:{self.srv.server_address[1]}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.clock = Clock()
        self.owner = None
        if setup:
            self.owner = self.client()
            s, t, url = self.owner.req('/setup', {'school_name': 'Test School', 'address': '1 High St',
                                                  'currency': 'GBP', 'timezone': 'UTC', 'display_name': 'Owner',
                                                  'username': 'owner', 'password': PW, 'password2': PW})
            assert url.endswith('/'), (s, url, t[:500])

    def client(self):
        return Client(self.base)

    def close(self):
        self.clock.close()
        self.srv.shutdown()
        self.srv.server_close()

    # --- direct DB reads (for ids and checking stored state)
    def q(self, sql, *args):
        c = sqlite3.connect(self.cfg['db_path'] if 'db_path' in self.cfg else os.path.join(self.data_dir, 'lessonledger.db'))
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(sql, args)]
        finally:
            c.close()

    def last_id(self, table):
        return self.q(f'SELECT MAX(id) m FROM {table}')[0]['m']

    # --- HTTP helpers as owner (or given client)
    def rec(self, kind, cl=None, **f):
        cl = cl or self.owner
        cl.get(f'/directory/{kind}/new')
        s, t, url = cl.req(f'/directory/{kind}/new', dict(f, action='save'))
        return t, url

    def setting(self, **kv):
        cl = self.owner
        s, t, _ = cl.get('/admin/settings')
        cur = {}
        cur.update(kv)
        cur.pop('csrf', None)
        return cl.req('/admin/settings', cur)

    def basic(self, price='21.00', duration='30', max_pupils='1'):
        """teacher, room, type, family, pupil; returns ids dict"""
        ids = {}
        self.rec('teachers', name='Mr Jones'); ids['teacher'] = self.last_id('teachers')
        self.rec('teachers', name='Ms Lee'); ids['teacher2'] = self.last_id('teachers')
        self.rec('rooms', name='Room 2'); ids['room'] = self.last_id('rooms')
        self.rec('rooms', name='Room 3'); ids['room2'] = self.last_id('rooms')
        self.rec('lesson_types', name='Piano 30', duration=duration, price=price, max_pupils=max_pupils)
        ids['type'] = self.last_id('lesson_types')
        self.rec('families', name='Smith Family', address='2 Road', email='s@example.com')
        ids['family'] = self.last_id('families')
        self.rec('families', name='Brown Family')
        ids['family2'] = self.last_id('families')
        self.rec('pupils', name='Anna Smith', family_id=str(ids['family'])); ids['pupil'] = self.last_id('pupils')
        self.rec('pupils', name='Ben Brown', family_id=str(ids['family2'])); ids['pupil2'] = self.last_id('pupils')
        return ids

    def term(self, name='Autumn 2026', first='2026-09-07', last='2026-12-18', cl=None):
        cl = cl or self.owner
        cl.get('/terms')
        s, t, url = cl.req('/terms', {'action': 'save', 'name': name, 'first_day': first, 'last_day': last})
        return t, url, self.last_id('terms')

    def skip(self, tid, start, end='', label='Half-term'):
        cl = self.owner
        cl.get(f'/terms/{tid}')
        return cl.req(f'/terms/{tid}', {'action': 'add_skip', 'start': start, 'end': end, 'label': label})

    def slot(self, tid, weekday, start, type_id, teacher, room, pupils, start_date='', end_date='', cl=None):
        cl = cl or self.owner
        cl.get(f'/slots/new?term={tid}')
        s, t, url = cl.req(f'/slots/new?term={tid}', {'term': tid, 'weekday': weekday, 'start': start,
                                                      'lesson_type_id': type_id, 'teacher_id': teacher,
                                                      'room_id': room, 'pupils': [str(p) for p in pupils],
                                                      'start_date': start_date, 'end_date': end_date})
        return t, url

    def inv_action(self, tid, action, cl=None):
        cl = cl or self.owner
        cl.get(f'/invoices?term={tid}')
        return cl.req(f'/invoices?term={tid}', {'action': action, 'term': tid})

    def invoice(self, iid, action, cl=None, **f):
        cl = cl or self.owner
        cl.get(f'/invoices/{iid}')
        return cl.req(f'/invoices/{iid}', dict(f, action=action))

    def occ(self, tid, slot, date, action, reason='x', cl=None):
        cl = cl or self.owner
        cl.get(f'/lessons?term={tid}')
        return cl.req(f'/lessons?term={tid}', {'slot': slot, 'date': date, 'action': action, 'reason': reason,
                                                'term': tid})

    def invoices(self, tid=None):
        return self.q('SELECT * FROM invoices' + (f' WHERE term_id={tid}' if tid else '') + ' ORDER BY id')


def has_error(text):
    return 'class="errors"' in text or 'class="err"' in text


def txt(t):
    return re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', t.split('</style>')[-1]))
