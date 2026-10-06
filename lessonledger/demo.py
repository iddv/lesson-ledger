"""Demo data, loaded only into an empty database by the explicit `demo` command."""
import datetime as dt
import random
import secrets

from . import core

FIRST = ['Anna', 'Ben', 'Chloe', 'Daniel', 'Ella', 'Finn', 'Grace', 'Harry', 'Isla', 'Jack', 'Kate', 'Leo', 'Maya',
         'Noah', 'Olivia', 'Priya', 'Quinn', 'Ruby', 'Sam', 'Tara', 'Umar', 'Vera', 'Will', 'Zara']
LAST = ['Smith', 'Jones', 'Patel', 'Brown', 'Taylor', 'Wilson', 'Evans', 'Khan', 'Wright', 'Hughes', 'Green', 'Hall',
        'Wood', 'Clarke', 'Lewis', 'Young', 'King', 'Hill', 'Moore', 'Scott', 'Baker', 'Adams', 'Ali', 'Turner',
        'Cooper', 'Ward', 'Morris', 'Price', 'Bell', 'Reid', 'Cook', 'Shaw', 'Mills', 'Fox', 'Lee', 'Nash', 'Owen',
        'Ross', 'Day', 'Hart']


def monday(x):
    return x - dt.timedelta(days=x.weekday())


def load(c):
    if not core.is_empty(c):
        raise core.Invalid('The database already has data. The demo command only works on an empty database.')
    rnd = random.Random(42)
    if core.needs_setup(c):
        for k, v in (('school.name', 'Harmony Music School'), ('school.address', '12 High Street\nLowtown LT1 2AB'),
                     ('school.currency', 'GBP'), ('school.timezone', core.server_timezone())):
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (k, v))
    creds = []
    for name, role in (('admin', 'admin'), ('staff', 'staff')):
        if core.row(c, 'SELECT 1 FROM users WHERE username=?', name):
            continue
        pw = secrets.token_urlsafe(9)
        c.execute('INSERT INTO users(username,display_name,role,pw_hash,must_change,created_at) VALUES (?,?,?,?,1,?)',
                  (name, f'Demo {role}', role, core.hash_password(pw), core.now_iso()))
        creds.append((name, pw))
    sys = None
    T = [core.save_record(c, sys, 'teachers', {'name': n, 'email': f'{n.split()[-1].lower()}@example.org',
                                               'phone': f'07700 9000{i}', 'colour': col})
         for i, (n, col) in enumerate([('Mr Jones', '#4a90d9'), ('Ms Patel', '#d94a7a'), ('Mrs Clarke', '#3fa96b'),
                                       ('Mr Okafor', '#e09b2d'), ('Ms Novak', '#8c5bd6'), ('Mr Hughes', '#2bb3b3')])]
    R = [core.save_record(c, sys, 'rooms', {'name': n}) for n in ('Room 1', 'Room 2', 'Room 3', 'Studio', 'Hall')]
    LT = [core.save_record(c, sys, 'lesson_types', {'name': n, 'duration': str(du), 'price': p, 'max_pupils': str(m)})
          for n, du, p, m in (('Piano 30', 30, '21.00', 1), ('Piano 45', 45, '30.00', 1), ('Violin 30', 30, '21.00', 1),
                              ('Guitar 30', 30, '20.00', 1), ('Voice 45', 45, '29.00', 1),
                              ('Junior Ensemble', 60, '8.50', 8))]
    fams, pupils = [], []
    for i in range(40):
        last = LAST[i]
        f = core.save_record(c, sys, 'families', {'name': f'{rnd.choice(FIRST)} {last}',
                                                  'address': f'{i + 3} Mill Lane\nLowtown LT{i % 9 + 1} {i % 7}CD',
                                                  'email': f'{last.lower()}{i}@example.com', 'phone': f'01632 960{i:03d}'})
        fams.append(f)
    instruments = ['Piano', 'Piano', 'Violin', 'Guitar', 'Voice']
    for i in range(60):
        fam = fams[i % 40]
        last = LAST[i % 40]
        pupils.append(core.save_record(c, sys, 'pupils', {
            'name': f'{FIRST[(i * 7) % len(FIRST)]} {last}', 'instrument': instruments[i % 5], 'family_id': str(fam),
            'dob': f'{2010 + i % 9}-{i % 12 + 1:02d}-{i % 27 + 1:02d}'}))
    today = core.today(c)
    cur_start = monday(today) - dt.timedelta(weeks=5)
    cur_end = cur_start + dt.timedelta(weeks=14) - dt.timedelta(days=3)
    past_start = cur_start - dt.timedelta(weeks=16)
    past_end = cur_start - dt.timedelta(weeks=3, days=3)
    past = core.save_term(c, sys, {'name': f'Previous term {past_start.year}', 'first_day': past_start.isoformat(),
                                   'last_day': past_end.isoformat()})
    cur = core.save_term(c, sys, {'name': f'Current term {cur_start.year}', 'first_day': cur_start.isoformat(),
                                  'last_day': cur_end.isoformat()})
    ht = cur_start + dt.timedelta(weeks=7)
    core.add_skip(c, sys, cur, {'start': ht.isoformat(), 'end': (ht + dt.timedelta(days=4)).isoformat(),
                                'label': 'Half-term'})
    bh = cur_start + dt.timedelta(weeks=3)
    core.add_skip(c, sys, cur, {'start': bh.isoformat(), 'label': 'Bank holiday'})
    pht = past_start + dt.timedelta(weeks=6)
    core.add_skip(c, sys, past, {'start': pht.isoformat(), 'end': (pht + dt.timedelta(days=4)).isoformat(),
                                 'label': 'Half-term'})

    def build(tid, target):
        made, k = 0, 0
        # Saturday ensemble groups of 8 pupils
        for g in range(2):
            group = pupils[g * 8:(g + 1) * 8]
            core.create_slot(c, sys, tid, {'weekday': 5, 'start': f'{10 + g}:00', 'lesson_type_id': LT[5],
                                           'teacher_id': T[4 + g], 'room_id': R[4], 'pupils': group})
            made += 1
        for wd in range(5):
            for ri, room in enumerate(R[:4] + [R[4]]):
                teacher = T[(ri + wd) % 6]
                mins = 15 * 60
                while mins < 20 * 60 and made < target:
                    lt = LT[(k + ri) % 5]
                    pupil = pupils[k % 60]
                    k += 1
                    try:
                        c.execute('SAVEPOINT demo')
                        core.create_slot(c, sys, tid, {'weekday': wd, 'start': core.hm(mins), 'lesson_type_id': lt,
                                                       'teacher_id': teacher, 'room_id': room, 'pupils': [pupil]})
                        c.execute('RELEASE demo')
                        made += 1
                    except core.Invalid:
                        c.execute('ROLLBACK TO demo')
                        c.execute('RELEASE demo')
                    mins += core.row(c, 'SELECT duration FROM lesson_types WHERE id=?', lt)['duration']
        return made

    build(past, 80)
    build(cur, 90)
    # past term: invoices issued, most paid, some part-paid, one credited, one voided
    core.TODAY_OVERRIDE = past_end + dt.timedelta(days=2)
    try:
        core.generate_drafts(c, sys, past)
        drafts = core.rows(c, "SELECT id FROM invoices WHERE term_id=? ORDER BY id", past)
        core.add_adjustment(c, sys, drafts[0]['id'], {'description': 'Sibling discount', 'amount': '-10.00'})
        core.issue_all(c, sys, past)
        invs = core.list_invoices(c, tid=past)
        pay_day = (past_end + dt.timedelta(days=2)).isoformat()
        for n, inv in enumerate(invs):
            if n == 0:
                core.void_invoice(c, sys, inv['id'], 'Issued to the wrong family address')
            elif n == 1:
                core.credit_note(c, sys, inv['id'], {'reason': 'Teacher illness', 'lines': 'Lesson cancelled | 21.00'})
                core.mark_paid(c, sys, inv['id'], 'bank transfer')
            elif n % 5 == 2:
                core.record_payment(c, sys, inv['id'], {'amount': '50.00', 'method': 'cash', 'date': pay_day})
            elif n % 7 != 3:
                core.record_payment(c, sys, inv['id'], {'amount': f'{inv["total"] / 100:.2f}', 'date': pay_day,
                                                        'method': ['bank transfer', 'card', 'cheque'][n % 3]})
    finally:
        core.TODAY_OVERRIDE = None
    # current term: a few cancelled lessons
    t = core.term(c, cur)
    skip = core.skipped_dates(c, cur)
    for s in core.rows(c, 'SELECT * FROM slots WHERE term_id=? ORDER BY id LIMIT 4', cur):
        x = core.slot_dates(t, s, skip)[1]
        core.set_occurrence(c, sys, s['id'], x.isoformat(), 'cancel', 'Teacher unwell')
    return creds
