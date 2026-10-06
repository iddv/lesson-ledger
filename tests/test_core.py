import datetime as dt
import os
import sqlite3
import tempfile
import unittest

from lessonledger import core, db, demo
from lessonledger.core import Invalid, Forbidden


def make_cfg(tmp):
    return db.load_config({'LL_DATA_DIR': os.path.join(tmp, 'data'), 'LL_CONFIG': os.path.join(tmp, 'none.conf')})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = make_cfg(self.tmp)
        self.c = db.open_db(self.cfg)
        core.TODAY_OVERRIDE = dt.date(2026, 9, 1)
        with db.tx(self.c):
            self.admin = core.setup(self.c, {'school_name': 'Test School', 'currency': 'GBP', 'timezone': 'UTC',
                                             'username': 'owner', 'password': 'correct horse', 'password2': 'correct horse'})
            uid = core.create_user(self.c, self.admin, {'username': 'staff1', 'display_name': 'Staff', 'role': 'staff',
                                                        'password': 'temporary-pw'})
        self.staff = core.row(self.c, 'SELECT * FROM users WHERE id=?', uid)
        # Autumn term Mon 7 Sep – Fri 18 Dec 2026 with half-term 26–30 Oct
        self.term = self.w(core.save_term, {'name': 'Autumn 2026', 'first_day': '2026-09-07', 'last_day': '2026-12-18'})
        self.w(core.add_skip, self.term, {'start': '2026-10-26', 'end': '2026-10-30', 'label': 'Half-term'})
        rec = lambda k, **f: self.w(core.save_record, k, {kk: str(v) for kk, v in f.items()})  # noqa: E731
        self.t1, self.t2 = rec('teachers', name='Mr Jones'), rec('teachers', name='Ms Patel')
        self.r1, self.r2 = rec('rooms', name='Room 1'), rec('rooms', name='Room 2')
        self.piano = rec('lesson_types', name='Piano 30', duration=30, price='21.00', max_pupils=1)
        self.group = rec('lesson_types', name='Ensemble', duration=60, price='8.50', max_pupils=3)
        self.f1, self.f2 = rec('families', name='Smith family'), rec('families', name='Brown family')
        self.anna = rec('pupils', name='Anna Smith', family_id=self.f1)
        self.tom = rec('pupils', name='Tom Smith', family_id=self.f1)
        self.bea = rec('pupils', name='Bea Brown', family_id=self.f2)

    def tearDown(self):
        core.TODAY_OVERRIDE = None
        self.c.close()

    def w(self, fn, *a, actor='staff', **kw):
        with db.tx(self.c):
            return fn(self.c, getattr(self, actor), *a, **kw)

    def slot(self, wd=1, start='16:00', lt=None, teacher=None, room=None, pupils=(), **kw):
        f = {'weekday': wd, 'start': start, 'lesson_type_id': lt or self.piano, 'teacher_id': teacher or self.t1,
             'room_id': room or self.r1, 'pupils': list(pupils)}
        f.update(kw)
        return self.w(core.create_slot, self.term, f)


class TestConflicts(Base):
    def test_room_teacher_pupil_clashes_each_reported(self):
        self.slot(pupils=[self.anna])
        with self.assertRaises(Invalid) as e:
            self.slot(start='16:15', pupils=[self.anna])
        msgs = e.exception.errors['_']
        self.assertEqual(len(msgs), 3)
        self.assertIn('Room 1 is booked Tue 16:00–16:30 by Piano 30 (Mr Jones, Anna Smith).', msgs)
        self.assertTrue(any(m.startswith('Mr Jones is teaching') for m in msgs))
        self.assertTrue(any(m.startswith('Anna Smith already has') for m in msgs))
        self.assertEqual(core.row(self.c, 'SELECT COUNT(*) n FROM slots')['n'], 1)

    def test_back_to_back_is_fine(self):
        self.slot(start='16:00', pupils=[self.anna])
        self.slot(start='16:30', pupils=[self.anna])
        self.slot(start='15:30', pupils=[self.anna])

    def test_only_pupil_clash(self):
        self.slot(pupils=[self.anna])
        with self.assertRaises(Invalid) as e:
            self.slot(teacher=self.t2, room=self.r2, pupils=[self.anna])
        self.assertEqual(len(e.exception.errors['_']), 1)

    def test_other_weekday_no_clash(self):
        self.slot(wd=1)
        self.slot(wd=2)

    def test_date_ranges(self):
        self.slot(end_date='2026-10-20')
        # starts the day after: no overlap
        self.slot(start_date='2026-10-21')
        with self.assertRaises(Invalid):
            self.slot(start_date='2026-10-20', end_date='2026-10-20', room=self.r1, teacher=self.t2)

    def test_edit_rechecked_and_capacity_hours_archived(self):
        a = self.slot(pupils=[self.anna])
        b = self.slot(start='17:00', teacher=self.t2, room=self.r2)
        with self.assertRaises(Invalid):
            self.w(core.update_slot, b, {'weekday': 1, 'start': '16:00', 'lesson_type_id': self.piano,
                                         'teacher_id': self.t2, 'room_id': self.r1, 'pupils': []})
        with self.assertRaises(Invalid) as e:
            self.slot(wd=3, pupils=[self.anna, self.tom])
        self.assertIn('pupils', e.exception.errors)
        with self.assertRaises(Invalid) as e:
            self.slot(wd=3, start='21:45')
        self.assertIn('start', e.exception.errors)
        with self.assertRaises(Invalid):  # archive refused while slot is live
            self.w(core.set_archived, 'teachers', self.t1, True)
        self.w(core.set_archived, 'rooms', self.r2, False)
        self.w(core.delete_slot, a)
        self.w(core.delete_slot, b)
        self.w(core.set_archived, 'teachers', self.t1, True)
        with self.assertRaises(Invalid):
            self.slot(wd=4)


class TestOccurrences(Base):
    def test_teaching_days_and_occurrences(self):
        weeks, per_day = core.term_calendar(self.c, self.term)
        self.assertEqual(len(weeks), 15)
        self.assertEqual(per_day[:5], [14, 14, 14, 14, 14])
        self.assertEqual(per_day[5:], [14, 14])  # weekends 12 Sep..13 Dec minus half-term
        s = core.get_slot(self.c, self.slot())
        dates = core.slot_dates(core.term(self.c, self.term), s, core.skipped_dates(self.c, self.term))
        self.assertEqual(len(dates), 14)
        self.assertNotIn(dt.date(2026, 10, 27), dates)
        sid = self.slot(wd=2, start_date='2026-10-01', end_date='2026-11-11')
        s = core.get_slot(self.c, sid)
        # Wednesdays 7,14,21 Oct, (28 skipped), 4, 11 Nov
        self.assertEqual(len(core.slot_dates(core.term(self.c, self.term), s, core.skipped_dates(self.c, self.term))), 5)

    def test_skip_outside_term_refused(self):
        with self.assertRaises(Invalid):
            self.w(core.add_skip, self.term, {'start': '2026-12-20', 'label': 'x'})
        with self.assertRaises(Invalid):
            self.w(core.save_term, {'name': 'Overlap', 'first_day': '2026-12-01', 'last_day': '2027-01-10'})
        with self.assertRaises(Invalid):
            self.w(core.save_term, {'name': 'Bad', 'first_day': '2027-02-01', 'last_day': '2027-01-10'})

    def test_cancel_and_restore(self):
        sid = self.slot(pupils=[self.anna])
        with self.assertRaises(Invalid):
            self.w(core.set_occurrence, sid, '2026-10-27', 'cancel', 'x')  # half-term
        self.w(core.generate_drafts, self.term)
        inv = core.row(self.c, 'SELECT * FROM invoices')
        self.assertEqual(core.invoice_figures(self.c, inv)['total'], 14 * 2100)
        self.w(core.set_occurrence, sid, '2026-09-08', 'cancel', 'Teacher ill')
        self.w(core.regenerate, self.term)
        self.assertEqual(core.invoice_figures(self.c, inv)['total'], 13 * 2100)
        self.w(core.set_occurrence, sid, '2026-09-08', 'restore')
        self.w(core.regenerate, self.term)
        self.assertEqual(core.invoice_figures(self.c, inv)['total'], 14 * 2100)

    def test_absence_setting(self):
        sid = self.slot(pupils=[self.anna])
        self.w(core.set_occurrence, sid, '2026-09-08', 'absent', 'ill')
        self.w(core.generate_drafts, self.term)
        inv = core.row(self.c, 'SELECT * FROM invoices')
        self.assertEqual(core.invoice_figures(self.c, inv)['total'], 14 * 2100)
        self.w(core.set_settings, {'billing.pupil_absence': 'no_charge'}, actor='admin')
        self.w(core.regenerate, self.term)
        self.assertEqual(core.invoice_figures(self.c, inv)['total'], 13 * 2100)


class TestInvoices(Base):
    def setUp(self):
        super().setUp()
        self.slot(pupils=[self.anna])
        self.slot(start='17:00', pupils=[self.tom])
        self.slot(wd=3, lt=self.group, pupils=[self.bea, self.anna])

    def test_generation_idempotent_and_lines(self):
        self.assertEqual(self.w(core.generate_drafts, self.term), 2)
        self.assertEqual(self.w(core.generate_drafts, self.term), 0)
        invs = core.list_invoices(self.c, tid=self.term)
        self.assertEqual(len(invs), 2)
        smith = [i for i in invs if i['family_id'] == self.f1][0]
        self.assertEqual(smith['total'], 14 * 2100 * 2 + 14 * 850)
        descs = [ln['description'] for ln in core.invoice_lines(self.c, smith['id'])]
        self.assertIn('Anna Smith – Piano 30 – Tue 16:00 – 14 lessons × £21.00 = £294.00', descs)
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("INSERT INTO invoices(term_id,family_id,status,created_at) VALUES (?,?,'draft','x')",
                           (self.term, self.f1))

    def test_adjustments_survive_regenerate_and_numbers_gapless(self):
        self.w(core.generate_drafts, self.term)
        a, b = [i['id'] for i in core.list_invoices(self.c, tid=self.term)]
        self.w(core.add_adjustment, a, {'description': 'Sibling discount', 'amount': '-10.00'})
        self.w(core.regenerate, self.term)
        self.assertEqual(len([ln for ln in core.invoice_lines(self.c, a) if ln['kind'] == 'adjustment']), 1)
        n, refused = self.w(core.issue_all, self.term)
        self.assertEqual((n, refused), (2, []))
        nums = sorted(r['number'] for r in core.rows(self.c, 'SELECT number FROM invoices'))
        self.assertEqual(nums, ['2026-0001', '2026-0002'])
        inv = core.get_invoice(self.c, a)
        self.assertEqual(inv['due_date'], '2026-09-15')
        with self.assertRaises(Invalid):
            self.w(core.add_adjustment, a, {'description': 'x', 'amount': '1'})
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute('DELETE FROM invoice_lines WHERE invoice_id=?', (a,))
        # term dates and slots locked by issued invoices
        with self.assertRaises(Invalid):
            self.w(core.add_skip, self.term, {'start': '2026-11-02', 'label': 'x'})
        sid = core.row(self.c, 'SELECT id FROM slots LIMIT 1')['id']
        with self.assertRaises(Invalid):
            self.w(core.set_occurrence, sid, '2026-09-08', 'cancel', 'x')
        with self.assertRaises(Invalid):
            self.w(core.delete_slot, sid)
        # void keeps number; regenerate a new draft; next number continues
        num_a = core.get_invoice(self.c, a)['number']
        with self.assertRaises(Forbidden):
            self.w(core.void_invoice, a, 'wrong')
        self.w(core.void_invoice, a, 'wrong', actor='admin')
        self.assertEqual(self.w(core.generate_drafts, self.term), 1)
        new = core.row(self.c, "SELECT id FROM invoices WHERE status='draft'")['id']
        self.assertEqual(self.w(core.issue, new), '2026-0003')
        self.assertEqual(core.get_invoice(self.c, a)['number'], num_a)

    def test_zero_total_refused(self):
        self.w(core.generate_drafts, self.term)
        a = core.list_invoices(self.c, tid=self.term)[0]
        self.w(core.add_adjustment, a['id'], {'description': 'Free term', 'amount': f'-{a["total"] / 100:.2f}'})
        with self.assertRaises(Invalid):
            self.w(core.issue, a['id'])

    def issued(self):
        self.w(core.generate_drafts, self.term)
        self.w(core.issue_all, self.term)
        inv = [i for i in core.list_invoices(self.c, tid=self.term) if i['family_id'] == self.f2][0]
        return inv['id']

    def fig(self, iid):
        return core.invoice_figures(self.c, core.get_invoice(self.c, iid))

    def test_balances(self):
        iid = self.issued()
        total = self.fig(iid)['total']
        self.assertEqual(total, 14 * 850)
        self.assertEqual(self.fig(iid)['status'], 'issued')
        with self.assertRaises(Invalid):  # overpayment rejected by default
            self.w(core.record_payment, iid, {'amount': '200.00', 'method': 'cash'})
        with self.assertRaises(Invalid):
            self.w(core.record_payment, iid, {'amount': '0', 'method': 'cash'})
        with self.assertRaises(Invalid):
            self.w(core.record_payment, iid, {'amount': '1.00', 'method': 'cash', 'date': '2026-09-02'})
        p = self.w(core.record_payment, iid, {'amount': '50.00', 'method': 'cash'})
        self.assertEqual(self.fig(iid)['status'], 'part-paid')
        self.assertEqual(self.fig(iid)['balance'], total - 5000)
        self.w(core.reverse_payment, p, 'typo')
        self.assertEqual(self.fig(iid)['balance'], total)
        with self.assertRaises(Invalid):
            self.w(core.reverse_payment, p, 'again')
        self.w(core.mark_paid, iid, 'card')
        self.assertEqual((self.fig(iid)['balance'], self.fig(iid)['status']), (0, 'paid'))
        with self.assertRaises(Invalid):
            self.w(core.void_invoice, iid, 'x', actor='admin')
        # credit after payment -> overpaid -> refund up to overpaid
        self.w(core.credit_note, iid, {'reason': 'Cancelled lesson', 'lines': 'Lesson 9 Sep | 8.50'})
        self.assertEqual(self.fig(iid)['balance'], -850)
        with self.assertRaises(Invalid):
            self.w(core.refund, iid, {'amount': '9.00', 'method': 'cash'})
        self.w(core.refund, iid, {'amount': '8.50', 'method': 'cash'})
        f = self.fig(iid)
        self.assertEqual((f['balance'], f['status']), (0, 'paid'))
        self.assertEqual(f['total'] - f['credited'] - f['payments'] + f['reversed'] + f['refunded'], f['balance'])
        with self.assertRaises(Invalid):  # credit larger than remaining total
            self.w(core.credit_note, iid, {'reason': 'x', 'lines': f'big | {total / 100:.2f}'})
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute('DELETE FROM entries')

    def test_overpayment_as_family_credit(self):
        self.w(core.set_settings, {'payments.overpayment': 'allow_credit'}, actor='admin')
        iid = self.issued()
        total = self.fig(iid)['total']
        self.w(core.record_payment, iid, {'amount': f'{(total + 1000) / 100:.2f}', 'method': 'cash'})
        self.assertEqual(self.fig(iid)['balance'], 0)
        self.assertEqual(core.family_credit(self.c, self.f2), 1000)

    def test_report_totals_match_balances(self):
        iid = self.issued()
        self.w(core.record_payment, iid, {'amount': '10.00', 'method': 'cash'})
        data, totals, overdue = core.term_report(self.c, self.term)
        invs = [i for i in core.list_invoices(self.c, tid=self.term) if i['status'] not in ('draft', 'void')]
        self.assertEqual(totals['outstanding'], sum(i['balance'] for i in invs))
        self.assertEqual(totals['invoiced'], sum(i['total'] for i in invs))
        self.assertEqual(overdue, 0)
        core.TODAY_OVERRIDE = dt.date(2026, 10, 1)
        self.assertEqual(core.term_report(self.c, self.term)[2], 2)
        es, by_method, by_day, total = core.payments_report(self.c, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        self.assertEqual(by_method, {'cash': 1000})
        self.assertEqual(total, sum(e['amount'] for e in es))
        with self.assertRaises(Invalid):
            core.parse_range(self.c, {'start': '2026-01-01', 'end': '2027-06-01'})


class TestUsersAndPermissions(Base):
    def test_lockout_and_must_change(self):
        u = core.login(self.c, 'staff1', 'temporary-pw')
        self.assertEqual(u['must_change'], 1)
        for _ in range(5):
            try:
                core.login(self.c, 'staff1', 'wrong')
            except Invalid as err:
                self.assertEqual(str(err), 'Invalid username or password.')
        with self.assertRaises(Invalid) as e:
            core.login(self.c, 'staff1', 'temporary-pw')
        self.assertIn('locked', str(e.exception))

    def test_last_admin_and_roles(self):
        with self.assertRaises(Invalid):
            self.w(core.update_user, self.admin['id'], {'role': 'staff'}, actor='admin')
        with self.assertRaises(Invalid):
            self.w(core.update_user, self.admin['id'], {'active': 0}, actor='admin')
        with self.assertRaises(Forbidden):
            self.w(core.create_user, {'username': 'x', 'display_name': 'x', 'role': 'staff', 'password': 'x' * 10})
        with self.assertRaises(Forbidden):
            self.w(core.set_settings, {'billing.pupil_absence': 'no_charge'})
        with self.assertRaises(Invalid) as e:
            self.w(core.create_user, {'username': 'staff1', 'display_name': 'x', 'role': 'staff',
                                      'password': 'x' * 10}, actor='admin')
        self.assertEqual(e.exception.errors['username'], 'Username already taken.')
        with self.assertRaises(Invalid):
            self.w(core.create_user, {'username': 'new', 'display_name': 'x', 'role': 'staff', 'password': 'short'},
                   actor='admin')
        # deactivation ends sessions and blocks login
        with db.tx(self.c):
            tok = core.create_session(self.c, self.staff)
        self.assertIsNotNone(core.get_session(self.c, tok))
        self.w(core.update_user, self.staff['id'], {'active': 0}, actor='admin')
        self.assertIsNone(core.get_session(self.c, tok))
        with self.assertRaises(Invalid):
            core.login(self.c, 'staff1', 'temporary-pw')

    def test_stale_edit_refused(self):
        rec = core.get_record(self.c, 'rooms', self.r1)
        self.w(core.save_record, 'rooms', {'name': 'Room A'}, self.r1, rec['version'])
        with self.assertRaises(Invalid) as e:
            self.w(core.save_record, 'rooms', {'name': 'Room B'}, self.r1, rec['version'])
        self.assertIn('changed since you opened it', str(e.exception))
        self.assertEqual(e.exception.current['name'], 'Room A')
        with self.assertRaises(Invalid):
            self.w(core.save_record, 'rooms', {'name': 'room 2'})
        with self.assertRaises(Invalid):
            self.w(core.save_record, 'lesson_types', {'name': 'X', 'duration': '10', 'price': '5', 'max_pupils': '1'})
        with self.assertRaises(Invalid):
            self.w(core.save_record, 'lesson_types', {'name': 'X', 'duration': '30', 'price': '-5', 'max_pupils': '1'})
        with self.assertRaises(Invalid) as e:
            self.w(core.save_record, 'lesson_types', {'name': 'Huge', 'duration': '30',
                                                      'price': '99999999999999999999.00', 'max_pupils': '1'})
        self.assertIn('price', e.exception.errors)
        self.assertIsNone(core.row(self.c, "SELECT 1 FROM lesson_types WHERE name='Huge'"))
        errs = {}
        self.assertIsNone(core.parse_money('99999999999999999999', 'amount', errs, allow_negative=True))
        self.assertIn('amount', errs)


class TestBackupRestore(Base):
    def test_round_trip_and_corrupt(self):
        self.slot(pupils=[self.anna])
        self.w(core.generate_drafts, self.term)
        self.w(core.issue_all, self.term)
        iid = core.row(self.c, 'SELECT id FROM invoices')['id']
        self.w(core.record_payment, iid, {'amount': '20.00', 'method': 'cash'})
        before = core.list_invoices(self.c)
        bfile = os.path.join(self.tmp, 'backup.db')
        db.backup_to(self.c, bfile)
        self.assertEqual(db.check_backup(bfile), db.LATEST)
        # restore onto a fresh install
        cfg2 = make_cfg(tempfile.mkdtemp())
        db.open_db(cfg2).close()
        db.restore(cfg2, bfile)
        c2 = db.open_db(cfg2)
        after = core.list_invoices(c2)
        self.assertEqual([(i['number'], i['total'], i['balance'], i['status']) for i in before],
                         [(i['number'], i['total'], i['balance'], i['status']) for i in after])
        for t in ('pupils', 'families', 'slots', 'entries', 'audit', 'users', 'settings'):
            self.assertEqual(core.row(self.c, f'SELECT COUNT(*) n FROM {t}')['n'],
                             core.row(c2, f'SELECT COUNT(*) n FROM {t}')['n'], t)
        # corrupt file refused, data untouched
        bad = os.path.join(self.tmp, 'bad.db')
        with open(bad, 'wb') as fh:
            fh.write(b'not a database' * 100)
        with self.assertRaises(db.BackupError):
            db.restore(cfg2, bad)
        c2.close()
        c3 = db.open_db(cfg2)
        self.assertEqual(len(core.list_invoices(c3)), len(before))
        # newer version refused
        newer = os.path.join(self.tmp, 'newer.db')
        db.backup_to(self.c, newer)
        x = sqlite3.connect(newer)
        x.execute(f'PRAGMA user_version={db.LATEST + 5}')
        x.close()
        with self.assertRaises(db.BackupError) as e:
            db.check_backup(newer)
        self.assertIn('newer version', str(e.exception))

    def test_auto_backup_rotation(self):
        self.cfg['backup_keep'] = 3
        for _ in range(5):
            db.write_backup(self.c, self.cfg)
        self.assertEqual(len([f for f in os.listdir(self.cfg['backup_dir']) if 'auto' in f]), 3)


class TestDemo(unittest.TestCase):
    def test_demo_loads_once(self):
        cfg = make_cfg(tempfile.mkdtemp())
        c = db.open_db(cfg)
        with db.tx(c):
            creds = demo.load(c)
        self.assertEqual([u for u, _ in creds], ['admin', 'staff'])
        self.assertEqual(core.row(c, 'SELECT COUNT(*) n FROM pupils')['n'], 60)
        statuses = {i['status'] for i in core.list_invoices(c)}
        self.assertTrue({'paid', 'part-paid', 'void'} <= statuses)
        with self.assertRaises(Invalid):
            with db.tx(c):
                demo.load(c)


if __name__ == '__main__':
    unittest.main()


class TestSettingEndWithinHours(Base):
    def tearDown(self):
        os.environ.pop('TIMETABLE_END_WITHIN_HOURS', None)
        super().tearDown()

    def test_whole_lesson_default(self):
        self.assertEqual(core.setting(self.c, 'timetable.end_within_hours'), 'whole_lesson')
        with self.assertRaises(Invalid) as e:
            self.slot(start='21:45')
        self.assertIn('start', e.exception.errors)
        self.slot(start='21:30')

    def test_start_only(self):
        self.w(core.set_settings, {'timetable.end_within_hours': 'start_only'}, actor='admin')
        self.slot(start='21:45')
        with self.assertRaises(Invalid):
            self.slot(start='22:00', room=self.r2, teacher=self.t2)
        with self.assertRaises(Invalid):
            self.slot(start='06:55', room=self.r2, teacher=self.t2)

    def test_env_override(self):
        os.environ['TIMETABLE_END_WITHIN_HOURS'] = 'start_only'
        self.slot(start='21:45')
        os.environ['TIMETABLE_END_WITHIN_HOURS'] = 'whole_lesson'
        self.w(core.set_settings, {'timetable.end_within_hours': 'start_only'}, actor='admin')
        with self.assertRaises(Invalid):
            self.slot(wd=2, start='21:45')


class TestSettingNumberYear(Base):
    def setUp(self):
        super().setUp()
        self.slot(pupils=[self.anna])
        self.w(core.generate_drafts, self.term)
        self.iid = core.row(self.c, 'SELECT id FROM invoices')['id']

    def tearDown(self):
        os.environ.pop('INVOICES_NUMBER_YEAR', None)
        super().tearDown()

    def test_issue_date_default(self):
        self.assertEqual(core.setting(self.c, 'invoices.number_year'), 'issue_date')
        self.assertEqual(self.w(core.issue, self.iid, '2027-01-04'), '2027-0001')

    def test_term_start(self):
        self.w(core.set_settings, {'invoices.number_year': 'term_start'}, actor='admin')
        self.assertEqual(self.w(core.issue, self.iid, '2027-01-04'), '2026-0001')

    def test_env_override(self):
        os.environ['INVOICES_NUMBER_YEAR'] = 'term_start'
        self.assertEqual(self.w(core.issue, self.iid, '2027-01-04'), '2026-0001')


class TestSettingArchiveFamily(Base):
    def setUp(self):
        super().setUp()
        self.slot(pupils=[self.anna])

    def tearDown(self):
        os.environ.pop('DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS', None)
        super().tearDown()

    def test_refused_default(self):
        self.assertEqual(core.setting(self.c, 'directory.archive_family_with_active_pupils'), 'refused')
        with self.assertRaises(Invalid) as e:
            self.w(core.set_archived, 'families', self.f1, True)
        self.assertTrue(any('Anna Smith' in m for m in e.exception.errors['_']))
        self.assertEqual(core.get_record(self.c, 'families', self.f1)['archived'], 0)
        self.w(core.set_archived, 'families', self.f2, True)  # no live slots

    def test_allowed(self):
        self.w(core.set_settings, {'directory.archive_family_with_active_pupils': 'allowed'}, actor='admin')
        self.w(core.set_archived, 'families', self.f1, True)
        self.assertEqual(core.get_record(self.c, 'families', self.f1)['archived'], 1)

    def test_env_override(self):
        os.environ['DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS'] = 'allowed'
        self.w(core.set_archived, 'families', self.f1, True)


class TestSettingPaymentBeforeIssue(Base):
    def setUp(self):
        super().setUp()
        self.slot(pupils=[self.anna])
        self.w(core.generate_drafts, self.term)
        self.iid = core.row(self.c, 'SELECT id FROM invoices')['id']
        self.w(core.issue, self.iid, '2026-08-20')

    def tearDown(self):
        os.environ.pop('PAYMENTS_BEFORE_ISSUE_DATE', None)
        super().tearDown()

    def pay(self, date):
        return self.w(core.record_payment, self.iid, {'amount': '5.00', 'method': 'cash', 'date': date})

    def test_allowed_default(self):
        self.assertEqual(core.setting(self.c, 'payments.before_issue_date'), 'allowed')
        self.pay('2026-08-01')

    def test_refused(self):
        self.w(core.set_settings, {'payments.before_issue_date': 'refused'}, actor='admin')
        with self.assertRaises(Invalid) as e:
            self.pay('2026-08-19')
        self.assertIn('date', e.exception.errors)
        self.pay('2026-08-20')
        self.assertEqual(core.row(self.c, 'SELECT COUNT(*) n FROM entries')['n'], 1)

    def test_env_override(self):
        os.environ['PAYMENTS_BEFORE_ISSUE_DATE'] = 'refused'
        with self.assertRaises(Invalid):
            self.pay('2026-08-01')
