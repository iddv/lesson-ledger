"""End-to-end tests through HTTP: setup, login, permissions, and every page renders."""
import http.cookiejar
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from lessonledger import core, db, demo, web


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


class TestWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        cls.cfg = db.load_config({'LL_DATA_DIR': os.path.join(tmp, 'd'), 'LL_PORT': '0',
                                  'LL_CONFIG': os.path.join(tmp, 'none')})
        db.open_db(cls.cfg).close()
        cls.srv = web.make_server(cls.cfg)
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_flow(self):
        a = Client(self.base)
        s, t, url = a.req('/')
        self.assertTrue(url.endswith('/setup'))
        s, t, _ = a.req('/setup', {'school_name': 'X', 'username': 'owner', 'password': 'short', 'password2': 'short'})
        self.assertIn('at least 10 characters', t)
        s, t, _ = a.req('/setup', {'school_name': 'X', 'username': 'owner', 'password': 'abcdefghij',
                                   'password2': 'abcdefghik'})
        self.assertIn('The two passwords differ', t)
        s, t, url = a.req('/setup', {'school_name': 'Harmony', 'currency': 'GBP', 'username': 'owner',
                                     'password': 'owner-password', 'password2': 'owner-password'})
        self.assertEqual(s, 200)
        self.assertIn('Dashboard', t)
        self.assertIn('./run.sh demo', t)
        # demo data straight into the database (users exist, records empty)
        c = db.connect(self.cfg['db_path'])
        with db.tx(c):
            creds = dict(demo.load(c))
        with self.assertRaises(core.Invalid):
            with db.tx(c):
                demo.load(c)
        # create a staff user who must change password
        a.req('/admin/users')
        s, t, _ = a.req('/admin/users', {'action': 'add', 'username': 'jo', 'display_name': 'Jo', 'role': 'staff',
                                         'password': 'temp-password-1'})
        self.assertIn('User added', t)
        st = Client(self.base)
        s, t, url = st.req('/login', {'username': 'jo', 'password': 'temp-password-1'})
        self.assertTrue(url.endswith('/password'))
        s, t, url = st.req('/invoices')
        self.assertTrue(url.endswith('/password'))
        s, t, url = st.req('/password', {'old': 'temp-password-1', 'password': 'new-password-22',
                                         'password2': 'new-password-22'})
        self.assertIn('Password changed', t)
        # staff cannot reach admin pages
        for p in ('/admin', '/admin/users', '/admin/settings', '/admin/backup', '/admin/audit',
                  '/admin/backup/download'):
            self.assertEqual(st.req(p)[0], 403, p)
        # CSRF required
        st.csrf = 'bogus'
        self.assertEqual(st.req('/terms', {'name': 'x'})[0], 403)
        st.req('/')
        # every page renders for staff and admin
        tid = c.execute('SELECT id FROM terms ORDER BY first_day DESC').fetchone()[0]
        inv = c.execute("SELECT id FROM invoices WHERE status='issued'").fetchone()[0]
        draft_tid = c.execute('SELECT id FROM terms ORDER BY first_day').fetchone()[0]
        sid = c.execute('SELECT id FROM slots WHERE term_id=?', (tid,)).fetchone()[0]
        pages = ['/', f'/terms', f'/terms/{tid}', f'/timetable?term={tid}', f'/timetable?term={tid}&view=teacher',
                 f'/timetable/print?term={tid}&room_id=1', f'/slots/new?term={tid}', f'/slots/{sid}',
                 f'/lessons?term={tid}', f'/invoices?term={draft_tid}', f'/invoices/{inv}', f'/invoices/{inv}/print',
                 f'/invoices/print?term={draft_tid}', '/payments', '/payments?start=2020-01-01&end=2020-12-31',
                 f'/reports?term={draft_tid}', f'/reports/teachers?term={tid}', '/families/1', '/password']
        for k in core.ENTITIES:
            pages += [f'/directory/{k}', f'/directory/{k}/new', f'/directory/{k}/1', f'/directory/{k}?archived=1&q=a']
        for p in pages:
            for who in (st, a):
                s, t, _ = who.req(p)
                self.assertEqual(s, 200, (p, t[-500:]))
        for p in ('/admin', '/admin/users', '/admin/settings', '/admin/backup', '/admin/audit',
                  '/admin/audit?entity=invoices&entity_id=1'):
            self.assertEqual(a.req(p)[0], 200, p)
        s, t, _ = a.req('/admin/backup/download')
        self.assertTrue(t.startswith('SQLite format 3'))
        s, t, _ = st.req(f'/reports?term={draft_tid}&csv=1')
        self.assertTrue(t.startswith('Family,Invoices,Invoiced'))
        s, t, _ = st.req('/payments?csv=1&start=2020-01-01&end=2020-12-31')
        self.assertTrue(t.startswith('Date,Kind'))
        s, t, _ = st.req('/payments?start=2026-05-01&end=2026-01-01')
        self.assertIn('ends before it starts', t)
        # a clashing slot through the form shows the clash
        s0 = core.get_slot(c, sid)
        st.req(f'/slots/new?term={tid}')
        s, t, _ = st.req(f'/slots/new?term={tid}', {'weekday': s0['weekday'], 'start': core.hm(s0['start_min']),
                                                    'lesson_type_id': s0['lesson_type_id'],
                                                    'teacher_id': s0['teacher_id'], 'room_id': s0['room_id']})
        self.assertIn('is booked', t)
        # cancel a lesson from the dated list
        occ = core.list_occurrences(c, tid, date_from='2000-01-01')[-1]
        st.req(f'/lessons?term={tid}')
        s, t, _ = st.req(f'/lessons?term={tid}', {'slot': occ['slot']['id'], 'date': occ['date'], 'action': 'cancel',
                                                  'reason': 'Snow day', 'back': f'/lessons?term={tid}'})
        self.assertIn('Lesson updated', t)
        self.assertEqual(c.execute("SELECT reason FROM occurrence_status WHERE date=? AND slot_id=?",
                                   (occ['date'], occ['slot']['id'])).fetchone()[0], 'Snow day')
        # staff void refused under the default admin_only setting
        st.req(f'/invoices/{inv}')
        s, t, _ = st.req(f'/invoices/{inv}', {'action': 'void', 'reason': 'x'})
        self.assertIn('Only an admin can void invoices', t)
        # lockout after 5 failures
        bad = Client(self.base)
        for _ in range(5):
            self.assertIn('Invalid username or password', bad.req('/login', {'username': 'jo', 'password': 'nope'})[1])
        s, t, _ = bad.req('/login', {'username': 'jo', 'password': 'new-password-22'})
        self.assertIn('locked', t)
        # deactivation ends the session
        a.req('/admin/users')
        uid = c.execute("SELECT id FROM users WHERE username='jo'").fetchone()[0]
        a.req('/admin/users', {'action': 'deactivate', 'user': uid})
        self.assertTrue(st.req('/')[2].endswith('/login?next=/'))
        c.close()
        # login refuses to redirect off-site (backslash and protocol-relative targets)
        import http.client
        port = self.srv.server_address[1]
        for target in ('/\\evil.example', '//evil.example', 'http://evil.example', '/ok/../\\x'):
            hc = http.client.HTTPConnection('127.0.0.1', port)
            hc.request('POST', '/login', urllib.parse.urlencode(
                {'username': 'owner', 'password': 'owner-password', 'next': target}),
                {'Content-Type': 'application/x-www-form-urlencoded'})
            r = hc.getresponse()
            self.assertEqual((r.status, r.getheader('Location')), (303, '/'), target)
            hc.close()
        # changing your password ends your other sessions but keeps this one
        b1, b2 = Client(self.base), Client(self.base)
        for b in (b1, b2):
            b.req('/login', {'username': 'owner', 'password': 'owner-password'})
            self.assertTrue(b.req('/')[2].endswith('/'))
        b1.req('/password')
        b1.req('/password', {'old': 'owner-password', 'password': 'owner-password-2',
                             'password2': 'owner-password-2'})
        self.assertFalse(b1.req('/')[2].endswith('/login?next=/'))
        self.assertTrue(b2.req('/')[2].endswith('/login?next=/'))

    def test_negative_content_length_refused(self):
        import socket
        s = socket.create_connection(('127.0.0.1', self.srv.server_address[1]), timeout=5)
        s.sendall(b'POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: -1\r\n\r\naaaa')
        self.assertIn(b' 400 ', s.recv(100))
        s.close()

    def test_setup_refused_remotely(self):
        self.assertFalse(web.is_local('192.168.1.20'))
        self.assertTrue(web.is_local('127.0.0.1'))
        self.assertTrue(web.is_local('::1'))


if __name__ == '__main__':
    unittest.main()
