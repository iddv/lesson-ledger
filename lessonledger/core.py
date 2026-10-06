"""Domain rules: users, directory, terms, timetable, occurrences, invoices, payments, reports.

Every write function expects to run inside db.tx(), takes the acting user (a users row, or
None for the system) and raises Invalid with field-level messages; nothing is saved on error.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import time

DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
METHODS = ['cash', 'bank transfer', 'card', 'cheque', 'other']
CURRENCIES = {'GBP': '£', 'EUR': '€', 'USD': '$', 'AUD': 'A$', 'CAD': 'C$', 'NZD': 'NZ$', 'ZAR': 'R',
              'IEP': '€', 'CHF': 'CHF ', 'SEK': 'kr ', 'NOK': 'kr ', 'DKK': 'kr '}
DEFAULTS = {
    'school.name': '', 'school.address': '', 'school.currency': 'GBP', 'school.timezone': 'UTC',
    'billing.pupil_absence': 'charge', 'payments.overpayment': 'reject',
    'invoices.void_permission': 'admin_only', 'timetable.copy_pupils': 'copy',
    'timetable.end_within_hours': 'whole_lesson',
    'invoices.number_year': 'issue_date',
    'directory.archive_family_with_active_pupils': 'refused',
    'payments.before_issue_date': 'allowed',
    'hours.open': '07:00', 'hours.close': '22:00', 'invoices.due_days': '14',
    'auth.min_password': '10', 'auth.session_hours': '8', 'auth.lockout_attempts': '5',
    'auth.lockout_minutes': '15',
}
CHOICES = {
    'billing.pupil_absence': ['charge', 'no_charge'],
    'payments.overpayment': ['reject', 'allow_credit'],
    'invoices.void_permission': ['admin_only', 'any_staff'],
    'timetable.copy_pupils': ['copy', 'empty'],
    'timetable.end_within_hours': ['start_only', 'whole_lesson'],
    'invoices.number_year': ['issue_date', 'term_start'],
    'directory.archive_family_with_active_pupils': ['allowed', 'refused'],
    'payments.before_issue_date': ['allowed', 'refused'],
}
MAX_AMOUNT = 100_000_000  # 1,000,000.00 in minor units; keeps every amount well inside SQLite's integer range
TODAY_OVERRIDE = None  # tests may pin "today"


class Invalid(Exception):
    """Validation failure. errors maps a field name (or '_' for the whole form) to a message
    or a list of messages."""

    def __init__(self, errors, current=None):
        if isinstance(errors, str):
            errors = {'_': errors}
        self.errors = errors
        self.current = current
        super().__init__('; '.join(m for v in errors.values() for m in ([v] if isinstance(v, str) else v)))


class Forbidden(Exception):
    pass


# ---------------------------------------------------------------- helpers

def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def today(c=None):
    if TODAY_OVERRIDE:
        return TODAY_OVERRIDE
    if c is not None:
        try:
            from zoneinfo import ZoneInfo
            return dt.datetime.now(ZoneInfo(setting(c, 'school.timezone'))).date()
        except Exception:
            pass
    return dt.date.today()


def d(s):
    return s if isinstance(s, dt.date) else dt.date.fromisoformat(s)


def parse_date(v, field, errors, required=True):
    v = (v or '').strip()
    if not v:
        if required:
            errors[field] = 'Enter a date.'
        return None
    try:
        return dt.date.fromisoformat(v)
    except ValueError:
        errors[field] = 'Enter a valid date (YYYY-MM-DD).'


def parse_money(v, field, errors, allow_negative=False, allow_zero=False):
    v = (str(v) if v is not None else '').strip().replace(',', '')
    for sym in set(CURRENCIES.values()):
        v = v.replace(sym.strip(), '')
    m = re.fullmatch(r'(-)?(\d+)(?:\.(\d{1,2}))?', v.strip())
    if not m:
        errors[field] = 'Enter an amount such as 21.00.'
        return None
    cents = int(m.group(2)) * 100 + int((m.group(3) or '0').ljust(2, '0'))
    if cents > MAX_AMOUNT:
        errors[field] = f'Enter an amount no larger than {MAX_AMOUNT // 100:,}.00.'
        return None
    if m.group(1):
        cents = -cents
    if cents < 0 and not allow_negative or cents == 0 and not allow_zero:
        errors[field] = 'Enter an amount above zero.' if not allow_negative else 'Enter a non-zero amount.'
        return None
    return cents


def parse_int(v, field, errors, lo, hi, label='a number'):
    try:
        n = int(str(v).strip())
    except (ValueError, TypeError):
        errors[field] = f'Enter {label}.'
        return None
    if not lo <= n <= hi:
        errors[field] = f'Must be between {lo} and {hi}.'
        return None
    return n


def parse_time(v, field, errors):
    m = re.fullmatch(r'(\d{1,2}):(\d{2})', (v or '').strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        errors[field] = 'Enter a time such as 16:00.'
        return None
    mins = int(m.group(1)) * 60 + int(m.group(2))
    if mins % 5:
        errors[field] = 'Start times must be on 5-minute steps.'
        return None
    return mins


def hm(mins):
    return f'{mins // 60:02d}:{mins % 60:02d}'


def money(cents, sym='£'):
    sign = '-' if cents < 0 else ''
    cents = abs(cents)
    return f'{sign}{sym}{cents // 100:,}.{cents % 100:02d}'


def currency_symbol(c):
    cur = setting(c, 'school.currency')
    return CURRENCIES.get(cur, cur + ' ')


def row(c, sql, *args):
    return c.execute(sql, args).fetchone()


def rows(c, sql, *args):
    return c.execute(sql, args).fetchall()


def as_dict(r):
    return dict(r) if r is not None else None


def audit(c, actor, action, entity, entity_id, before=None, after=None):
    for x in (before, after):
        if isinstance(x, dict):
            x.pop('pw_hash', None)
    c.execute('INSERT INTO audit(at,user_id,username,action,entity,entity_id,before,after) VALUES (?,?,?,?,?,?,?,?)',
              (now_iso(), actor['id'] if actor else None, actor['username'] if actor else 'system', action, entity,
               entity_id, json.dumps(before, default=str) if before is not None else None,
               json.dumps(after, default=str) if after is not None else None))


def require_admin(actor):
    if actor is not None and actor['role'] != 'admin':
        raise Forbidden('Only an admin can do that.')


# ---------------------------------------------------------------- settings

def env_override(key):
    """A switch can be forced by an environment variable named after its key, e.g.
    TIMETABLE_END_WITHIN_HOURS for timetable.end_within_hours. Read on every use."""
    v = os.environ.get(key.upper().replace('.', '_'), '').strip()
    return v if v in CHOICES.get(key, ()) else None


def setting(c, key):
    forced = env_override(key)
    if forced:
        return forced
    r = row(c, 'SELECT value FROM settings WHERE key=?', key)
    return r['value'] if r else DEFAULTS[key]


def all_settings(c):
    s = dict(DEFAULTS)
    s.update({r['key']: r['value'] for r in rows(c, 'SELECT key, value FROM settings')})
    s.update({k: env_override(k) for k in CHOICES if env_override(k)})
    return s


def set_settings(c, actor, values):
    require_admin(actor)
    errors = {}
    clean = {}
    for k, v in values.items():
        if k not in DEFAULTS:
            continue
        v = (v or '').strip()
        if k in CHOICES and v not in CHOICES[k]:
            errors[k] = 'Choose one of: ' + ', '.join(CHOICES[k])
        elif k == 'school.name' and not v:
            errors[k] = 'Enter the school name.'
        elif k == 'school.currency' and not re.fullmatch(r'[A-Z]{3}', v):
            errors[k] = 'Enter a 3-letter currency code such as GBP.'
        elif k == 'school.timezone' and not valid_tz(v):
            errors[k] = 'Enter a time zone such as Europe/London.'
        elif k in ('hours.open', 'hours.close') and parse_time(v, k, errors) is None:
            pass
        elif k in ('invoices.due_days', 'auth.min_password', 'auth.session_hours',
                   'auth.lockout_attempts', 'auth.lockout_minutes'):
            parse_int(v, k, errors, 1 if k != 'invoices.due_days' else 0, 365)
        clean[k] = v
    if not errors and 'hours.open' in clean and 'hours.close' in clean:
        if parse_time(clean['hours.open'], 'x', {}) >= parse_time(clean['hours.close'], 'x', {}):
            errors['hours.close'] = 'Closing time must be after opening time.'
    if errors:
        raise Invalid(errors)
    before = all_settings(c)
    for k, v in clean.items():
        c.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                  (k, v))
    audit(c, actor, 'update', 'settings', None, {k: before[k] for k in clean}, clean)


def valid_tz(name):
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:
        return False


def server_timezone():
    try:
        import os
        p = os.path.realpath('/etc/localtime')
        if '/zoneinfo/' in p:
            name = p.split('/zoneinfo/', 1)[1]
            if valid_tz(name):
                return name
    except OSError:
        pass
    return 'UTC'


# ---------------------------------------------------------------- users & auth

def hash_password(pw, salt=None, iters=120000):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), iters).hex()
    return f'pbkdf2${iters}${salt}${h}'


def check_password(pw, stored):
    try:
        _, iters, salt, h = stored.split('$')
        return hmac.compare_digest(hash_password(pw, salt, int(iters)), stored)
    except ValueError:
        return False


def _check_new_password(c, pw, pw2, errors, field='password'):
    n = int(setting(c, 'auth.min_password'))
    if len(pw or '') < n:
        errors[field] = f'Password must be at least {n} characters.'
    elif pw != pw2:
        errors[field + '2'] = 'The two passwords differ.'


def _check_username(c, username, errors):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{2,40}', username or ''):
        errors['username'] = 'Use 2–40 letters, digits, dots, dashes or underscores.'
    elif row(c, 'SELECT 1 FROM users WHERE username=?', username):
        errors['username'] = 'Username already taken.'


def needs_setup(c):
    return row(c, 'SELECT 1 FROM users') is None


def setup(c, f):
    if not needs_setup(c):
        raise Invalid('Setup has already been completed.')
    errors = {}
    if not f.get('school_name', '').strip():
        errors['school_name'] = 'Enter the school name.'
    cur = f.get('currency', 'GBP').strip().upper() or 'GBP'
    if not re.fullmatch(r'[A-Z]{3}', cur):
        errors['currency'] = 'Enter a 3-letter currency code such as GBP.'
    tz = f.get('timezone', '').strip() or server_timezone()
    if not valid_tz(tz):
        errors['timezone'] = 'Enter a time zone such as Europe/London.'
    username = f.get('username', '').strip()
    _check_username(c, username, errors)
    _check_new_password(c, f.get('password', ''), f.get('password2', ''), errors)
    if errors:
        raise Invalid(errors)
    for k, v in (('school.name', f['school_name'].strip()), ('school.address', f.get('address', '').strip()),
                 ('school.currency', cur), ('school.timezone', tz)):
        c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)', (k, v))
    c.execute('INSERT INTO users(username,display_name,role,pw_hash,created_at) VALUES (?,?,?,?,?)',
              (username, f.get('display_name', '').strip() or username, 'admin',
               hash_password(f['password']), now_iso()))
    u = row(c, 'SELECT * FROM users WHERE username=?', username)
    audit(c, u, 'setup', 'users', u['id'], None, {'username': username, 'role': 'admin', 'school': f['school_name']})
    return u


def create_user(c, actor, f):
    require_admin(actor)
    errors = {}
    username = f.get('username', '').strip()
    _check_username(c, username, errors)
    role = f.get('role', 'staff')
    if role not in ('admin', 'staff'):
        errors['role'] = 'Choose admin or staff.'
    if not f.get('display_name', '').strip():
        errors['display_name'] = 'Enter a display name.'
    _check_new_password(c, f.get('password', ''), f.get('password2', f.get('password', '')), errors)
    if errors:
        raise Invalid(errors)
    cur = c.execute('INSERT INTO users(username,display_name,role,pw_hash,must_change,created_at) VALUES (?,?,?,?,1,?)',
                    (username, f['display_name'].strip(), role, hash_password(f['password']), now_iso()))
    audit(c, actor, 'create', 'users', cur.lastrowid, None,
          {'username': username, 'display_name': f['display_name'].strip(), 'role': role})
    return cur.lastrowid


def _active_admins(c):
    return row(c, "SELECT COUNT(*) n FROM users WHERE role='admin' AND active=1")['n']


def update_user(c, actor, uid, f):
    require_admin(actor)
    u = as_dict(row(c, 'SELECT * FROM users WHERE id=?', uid))
    if not u:
        raise Invalid('No such user.')
    errors = {}
    name = f.get('display_name', u['display_name']).strip()
    role = f.get('role', u['role'])
    active = int(f.get('active', u['active']))
    if not name:
        errors['display_name'] = 'Enter a display name.'
    if role not in ('admin', 'staff'):
        errors['role'] = 'Choose admin or staff.'
    if u['role'] == 'admin' and u['active'] and (role != 'admin' or not active) and _active_admins(c) <= 1:
        errors['_'] = 'The last active admin cannot be demoted or deactivated.'
    if errors:
        raise Invalid(errors)
    c.execute('UPDATE users SET display_name=?, role=?, active=?, version=version+1 WHERE id=?',
              (name, role, active, uid))
    if not active:
        c.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
    if active and not u['active']:
        c.execute('UPDATE users SET failed=0, locked_until=0 WHERE id=?', (uid,))
    audit(c, actor, 'update', 'users', uid, {k: u[k] for k in ('display_name', 'role', 'active')},
          {'display_name': name, 'role': role, 'active': active})


def reset_password(c, actor, uid, pw):
    require_admin(actor)
    errors = {}
    _check_new_password(c, pw, pw, errors)
    if errors:
        raise Invalid(errors)
    c.execute('UPDATE users SET pw_hash=?, must_change=1, failed=0, locked_until=0 WHERE id=?',
              (hash_password(pw), uid))
    c.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
    audit(c, actor, 'reset_password', 'users', uid, None, {'must_change': 1})


def change_password(c, user, old, new, new2, keep_token=None):
    """Changes the user's password and ends all their other sessions (keep_token is the current one)."""
    errors = {}
    u = row(c, 'SELECT * FROM users WHERE id=?', user['id'])
    if not check_password(old or '', u['pw_hash']):
        errors['old'] = 'Current password is wrong.'
    _check_new_password(c, new, new2, errors)
    if not errors and new == old:
        errors['password'] = 'Choose a different password from the current one.'
    if errors:
        raise Invalid(errors)
    c.execute('UPDATE users SET pw_hash=?, must_change=0 WHERE id=?', (hash_password(new), u['id']))
    keep = _token_hash(c, keep_token) if keep_token else ''
    c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?', (u['id'], keep))
    audit(c, user, 'change_password', 'users', u['id'])


def login(c, username, pw):
    """Returns the user row or raises Invalid. Records failures and locks the account."""
    u = row(c, 'SELECT * FROM users WHERE username=?', (username or '').strip())
    bad = Invalid('Invalid username or password.')
    if not u:
        hash_password(pw or '')  # same work either way
        raise bad
    t = time.time()
    if u['locked_until'] > t:
        mins = int((u['locked_until'] - t) // 60) + 1
        raise Invalid(f'This account is locked after too many failed attempts. Try again in {mins} minutes.')
    if not check_password(pw or '', u['pw_hash']):
        failed = u['failed'] + 1
        locked = 0
        if failed >= int(setting(c, 'auth.lockout_attempts')):
            locked = t + 60 * int(setting(c, 'auth.lockout_minutes'))
            failed = 0
            audit(c, None, 'lockout', 'users', u['id'], None, {'username': u['username']})
        c.execute('UPDATE users SET failed=?, locked_until=? WHERE id=?', (failed, locked, u['id']))
        raise bad
    if not u['active']:
        raise bad
    c.execute('UPDATE users SET failed=0, locked_until=0 WHERE id=?', (u['id'],))
    return row(c, 'SELECT * FROM users WHERE id=?', u['id'])


def _token_hash(c, token):
    secret = row(c, "SELECT value FROM meta WHERE key='session_secret'")['value']
    return hmac.new(secret.encode(), token.encode(), 'sha256').hexdigest()


def create_session(c, user):
    token = secrets.token_urlsafe(32)
    c.execute('INSERT INTO sessions VALUES (?,?,?,?)', (_token_hash(c, token), user['id'],
                                                       secrets.token_urlsafe(16), time.time()))
    return token


def get_session(c, token):
    """Return (user, csrf) for a live session, refreshing its idle timer; else None."""
    if not token:
        return None
    th = _token_hash(c, token)
    s = row(c, 'SELECT * FROM sessions WHERE token_hash=?', th)
    if not s:
        return None
    if time.time() - s['last_seen'] > 3600 * float(setting(c, 'auth.session_hours')):
        c.execute('DELETE FROM sessions WHERE token_hash=?', (th,))
        return None
    u = row(c, 'SELECT * FROM users WHERE id=? AND active=1', s['user_id'])
    if not u:
        return None
    if time.time() - s['last_seen'] > 60:
        c.execute('UPDATE sessions SET last_seen=? WHERE token_hash=?', (time.time(), th))
    return u, s['csrf']


def end_session(c, token):
    if token:
        c.execute('DELETE FROM sessions WHERE token_hash=?', (_token_hash(c, token),))


# ---------------------------------------------------------------- directory

# field: (label, kind, required)
ENTITIES = {
    'teachers': ('Teacher', 'Teachers', [('name', 'Name', 'text', True), ('phone', 'Phone', 'text', False),
                                         ('email', 'Email', 'email', False), ('colour', 'Colour', 'color', False)]),
    'rooms': ('Room', 'Rooms', [('name', 'Name', 'text', True), ('notes', 'Notes', 'textarea', False)]),
    'lesson_types': ('Lesson type', 'Lesson types', [
        ('name', 'Name', 'text', True), ('duration', 'Duration (minutes)', 'int', True),
        ('price', 'Price per pupil per lesson', 'money', True), ('max_pupils', 'Maximum pupils', 'int', True)]),
    'families': ('Family', 'Families', [
        ('name', 'Billing name', 'text', True), ('address', 'Address', 'textarea', False),
        ('email', 'Email', 'email', False), ('phone', 'Phone', 'text', False), ('notes', 'Notes', 'textarea', False)]),
    'pupils': ('Pupil', 'Pupils', [
        ('name', 'Name', 'text', True), ('dob', 'Date of birth', 'date', False),
        ('instrument', 'Instrument', 'text', False), ('family_id', 'Family', 'family', True)]),
}


def validate_record(c, kind, f, rid=None):
    errors = {}
    out = {}
    for name, label, typ, req in ENTITIES[kind][2]:
        v = (f.get(name) or '').strip()
        if req and not v and not (name == 'max_pupils'):
            errors[name] = f'Enter the {label.lower()}.'
            continue
        if typ == 'int':
            if name == 'duration':
                out[name] = parse_int(v, name, errors, 15, 120, 'a number of minutes')
            else:
                out[name] = parse_int(v or '1', name, errors, 1, 12)
        elif typ == 'money':
            out[name] = parse_money(v, name, errors)
        elif typ == 'date':
            dd = parse_date(v, name, errors, required=False)
            out[name] = dd.isoformat() if dd else ''
            if dd and dd > today(c):
                errors[name] = 'Date of birth cannot be in the future.'
        elif typ == 'email':
            if v and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v):
                errors[name] = 'Enter a valid email address.'
            out[name] = v
        elif typ == 'color':
            if v and not re.fullmatch(r'#[0-9a-fA-F]{6}', v):
                errors[name] = 'Choose a colour.'
            out[name] = v or '#4a90d9'
        elif typ == 'family':
            fam = row(c, 'SELECT * FROM families WHERE id=?', v) if v.isdigit() else None
            if not fam:
                errors[name] = 'Choose a family.'
            elif fam['archived'] and not (rid and row(c, 'SELECT 1 FROM pupils WHERE id=? AND family_id=?', rid, fam['id'])):
                errors[name] = 'That family is archived.'
            out[name] = int(v) if v.isdigit() else None
        else:
            if len(v) > 2000:
                errors[name] = 'Too long.'
            out[name] = v
    if kind in ('rooms', 'lesson_types') and 'name' not in errors:
        if row(c, f'SELECT 1 FROM {kind} WHERE name=? AND id IS NOT ?', out['name'], rid):
            errors['name'] = f'A {ENTITIES[kind][0].lower()} with this name already exists.'
    if errors:
        raise Invalid(errors)
    return out


def get_record(c, kind, rid):
    return as_dict(row(c, f'SELECT * FROM {kind} WHERE id=?', rid))


def save_record(c, actor, kind, f, rid=None, version=None):
    data = validate_record(c, kind, f, rid)
    cols = list(data)
    if rid is None:
        cur = c.execute(f'INSERT INTO {kind}({",".join(cols)}) VALUES ({",".join("?" * len(cols))})',
                        [data[k] for k in cols])
        audit(c, actor, 'create', kind, cur.lastrowid, None, data)
        return cur.lastrowid
    before = get_record(c, kind, rid)
    if not before:
        raise Invalid('No such record.')
    cur = c.execute(f'UPDATE {kind} SET {",".join(k + "=?" for k in cols)}, version=version+1 '
                    f'WHERE id=? AND version=?', [data[k] for k in cols] + [rid, int(version or 0)])
    if cur.rowcount == 0:
        raise Invalid('This record changed since you opened it. The newer values are shown below.', current=before)
    audit(c, actor, 'update', kind, rid, {k: before[k] for k in cols}, data)
    return rid


def list_records(c, kind, q='', archived=False):
    sql = f'SELECT * FROM {kind} WHERE archived=? AND name LIKE ? ORDER BY name COLLATE NOCASE'
    return rows(c, sql, int(bool(archived)), f'%{q.strip()}%')


def describe_slot(c, s):
    s = row(c, '''SELECT s.*, lt.name type_name, t.name teacher_name, r.name room_name, tm.name term_name
                  FROM slots s JOIN lesson_types lt ON lt.id=s.lesson_type_id JOIN teachers t ON t.id=s.teacher_id
                  JOIN rooms r ON r.id=s.room_id JOIN terms tm ON tm.id=s.term_id WHERE s.id=?''', s['id'])
    pupils = ', '.join(p['name'] for p in slot_pupils(c, s['id']))
    return (f"{s['term_name']}: {DAYS[s['weekday']]} {hm(s['start_min'])}–{hm(s['start_min'] + s['duration'])} "
            f"{s['type_name']} in {s['room_name']} with {s['teacher_name']}" + (f' ({pupils})' if pupils else ''))


def _live_slots_using(c, kind, rid):
    col = {'teachers': 'teacher_id', 'rooms': 'room_id', 'lesson_types': 'lesson_type_id'}.get(kind)
    t = today(c).isoformat()
    if col:
        return rows(c, f'''SELECT s.* FROM slots s JOIN terms tm ON tm.id=s.term_id
                          WHERE s.{col}=? AND tm.last_day>=? AND s.end_date>=?''', rid, t, t)
    if kind == 'pupils':
        return rows(c, '''SELECT s.* FROM slots s JOIN slot_pupils sp ON sp.slot_id=s.id JOIN terms tm ON tm.id=s.term_id
                          WHERE sp.pupil_id=? AND tm.last_day>=? AND s.end_date>=?''', rid, t, t)
    if kind == 'families' and setting(c, 'directory.archive_family_with_active_pupils') == 'refused':
        return rows(c, '''SELECT DISTINCT s.* FROM slots s JOIN slot_pupils sp ON sp.slot_id=s.id
                          JOIN pupils p ON p.id=sp.pupil_id JOIN terms tm ON tm.id=s.term_id
                          WHERE p.family_id=? AND tm.last_day>=? AND s.end_date>=?''', rid, t, t)
    return []


def set_archived(c, actor, kind, rid, archived):
    before = get_record(c, kind, rid)
    if not before:
        raise Invalid('No such record.')
    if archived:
        live = _live_slots_using(c, kind, rid)
        if live:
            raise Invalid({'_': ['This record has slots in the current or a future term. End these first:'] +
                           [describe_slot(c, s) for s in live]})
    c.execute(f'UPDATE {kind} SET archived=?, version=version+1 WHERE id=?', (int(archived), rid))
    audit(c, actor, 'archive' if archived else 'restore', kind, rid, {'archived': before['archived']},
          {'archived': int(archived)})


def delete_record(c, actor, kind, rid):
    before = get_record(c, kind, rid)
    if not before:
        raise Invalid('No such record.')
    used = {
        'teachers': 'SELECT 1 FROM slots WHERE teacher_id=?',
        'rooms': 'SELECT 1 FROM slots WHERE room_id=?',
        'lesson_types': 'SELECT 1 FROM slots WHERE lesson_type_id=?',
        'pupils': 'SELECT 1 FROM slot_pupils WHERE pupil_id=? UNION SELECT 1 FROM invoice_lines WHERE pupil_id=?',
        'families': 'SELECT 1 FROM pupils WHERE family_id=? UNION SELECT 1 FROM invoices WHERE family_id=?',
    }[kind]
    if row(c, used, *([rid] * used.count('?'))):
        raise Invalid('This record has been used in the timetable or on invoices (or has pupils), so it can only be '
                      'archived.')
    c.execute(f'DELETE FROM {kind} WHERE id=?', (rid,))
    audit(c, actor, 'delete', kind, rid, before, None)


# ---------------------------------------------------------------- terms

def term(c, tid):
    t = as_dict(row(c, 'SELECT * FROM terms WHERE id=?', tid))
    if not t:
        raise Invalid('No such term.')
    return t


def skips(c, tid):
    return rows(c, 'SELECT * FROM skipped WHERE term_id=? ORDER BY start', tid)


def skipped_dates(c, tid):
    out = set()
    for s in skips(c, tid):
        x = d(s['start'])
        while x <= d(s['end']):
            out.add(x)
            x += dt.timedelta(days=1)
    return out


def current_term(c):
    t = today(c).isoformat()
    r = row(c, 'SELECT * FROM terms WHERE first_day<=? AND last_day>=?', t, t) or \
        row(c, 'SELECT * FROM terms WHERE first_day>? ORDER BY first_day LIMIT 1', t) or \
        row(c, 'SELECT * FROM terms ORDER BY last_day DESC LIMIT 1')
    return as_dict(r)


def _term_has_invoices(c, tid):
    return row(c, "SELECT 1 FROM invoices WHERE term_id=? AND status<>'void'", tid) is not None


def save_term(c, actor, f, tid=None, version=None):
    errors = {}
    name = (f.get('name') or '').strip()
    if not name:
        errors['name'] = 'Enter a term name.'
    first = parse_date(f.get('first_day'), 'first_day', errors)
    last = parse_date(f.get('last_day'), 'last_day', errors)
    if first and last:
        if last < first:
            errors['last_day'] = 'The last day is before the first day.'
        elif (last - first).days > 400:
            errors['last_day'] = 'A term cannot be longer than 400 days.'
        else:
            clash = row(c, 'SELECT name FROM terms WHERE first_day<=? AND last_day>=? AND id IS NOT ?',
                        last.isoformat(), first.isoformat(), tid)
            if clash:
                errors['first_day'] = f'These dates overlap the term "{clash["name"]}".'
    if errors:
        raise Invalid(errors)
    data = {'name': name, 'first_day': first.isoformat(), 'last_day': last.isoformat()}
    if tid is None:
        cur = c.execute('INSERT INTO terms(name,first_day,last_day) VALUES (?,?,?)', (name, data['first_day'],
                                                                                    data['last_day']))
        audit(c, actor, 'create', 'terms', cur.lastrowid, None, data)
        return cur.lastrowid
    before = term(c, tid)
    if before['closed']:
        raise Invalid('This term is closed.')
    if (before['first_day'], before['last_day']) != (data['first_day'], data['last_day']):
        if _term_has_invoices(c, tid):
            raise Invalid("Void the term's invoices first.")
        out = row(c, 'SELECT * FROM skipped WHERE term_id=? AND (start<? OR end>?)', tid, data['first_day'],
                  data['last_day'])
        if out:
            raise Invalid({'first_day': f'The skipped dates "{out["label"]}" would fall outside the term.'})
        if row(c, 'SELECT 1 FROM slots WHERE term_id=? AND (start_date<? OR end_date>?)', tid,
               data['first_day'], data['last_day']):
            # clamp slot ranges to the new dates
            c.execute('UPDATE slots SET start_date=MAX(start_date, ?), end_date=MIN(end_date, ?) WHERE term_id=?',
                      (data['first_day'], data['last_day'], tid))
            c.execute('DELETE FROM slots WHERE term_id=? AND start_date>end_date', (tid,))
    cur = c.execute('UPDATE terms SET name=?, first_day=?, last_day=?, version=version+1 WHERE id=? AND version=?',
                    (name, data['first_day'], data['last_day'], tid, int(version or 0)))
    if cur.rowcount == 0:
        raise Invalid('This record changed since you opened it. The newer values are shown below.', current=before)
    audit(c, actor, 'update', 'terms', tid, {k: before[k] for k in data}, data)
    return tid


def add_skip(c, actor, tid, f):
    t = term(c, tid)
    errors = {}
    start = parse_date(f.get('start'), 'start', errors)
    end = parse_date(f.get('end') or f.get('start'), 'end', errors)
    label = (f.get('label') or '').strip()
    if not label:
        errors['label'] = 'Enter a label, e.g. "Half-term".'
    if start and end:
        if end < start:
            errors['end'] = 'The end is before the start.'
        elif start < d(t['first_day']) or end > d(t['last_day']):
            errors['start'] = 'Skipped dates must be inside the term.'
    if errors:
        raise Invalid(errors)
    if t['closed']:
        raise Invalid('This term is closed.')
    if _term_has_invoices(c, tid):
        raise Invalid("Void the term's invoices first.")
    cur = c.execute('INSERT INTO skipped(term_id,start,end,label) VALUES (?,?,?,?)',
                    (tid, start.isoformat(), end.isoformat(), label))
    audit(c, actor, 'add_skip', 'terms', tid, None, {'start': start, 'end': end, 'label': label})
    return cur.lastrowid


def delete_skip(c, actor, skip_id):
    s = row(c, 'SELECT * FROM skipped WHERE id=?', skip_id)
    if not s:
        raise Invalid('No such skipped date.')
    if term(c, s['term_id'])['closed']:
        raise Invalid('This term is closed.')
    if _term_has_invoices(c, s['term_id']):
        raise Invalid("Void the term's invoices first.")
    c.execute('DELETE FROM skipped WHERE id=?', (skip_id,))
    audit(c, actor, 'delete_skip', 'terms', s['term_id'], dict(s), None)


def term_calendar(c, tid):
    """Teaching weeks (Monday, teaching-day count) and teaching days per weekday."""
    t = term(c, tid)
    skip = skipped_dates(c, tid)
    per_day = [0] * 7
    weeks = {}
    x = d(t['first_day'])
    while x <= d(t['last_day']):
        monday = x - dt.timedelta(days=x.weekday())
        weeks.setdefault(monday, 0)
        if x not in skip:
            per_day[x.weekday()] += 1
            weeks[monday] += 1
        x += dt.timedelta(days=1)
    return sorted(weeks.items()), per_day


def close_term(c, actor, tid):
    t = term(c, tid)
    if t['closed']:
        raise Invalid('This term is already closed.')
    for inv in rows(c, 'SELECT * FROM invoices WHERE term_id=?', tid):
        st = invoice_figures(c, inv)['status']
        if st not in ('paid', 'void'):
            raise Invalid('All invoices must be paid or void before the term can be closed.')
    c.execute('UPDATE terms SET closed=1, version=version+1 WHERE id=?', (tid,))
    audit(c, actor, 'close', 'terms', tid, {'closed': 0}, {'closed': 1})


def delete_term(c, actor, tid):
    t = term(c, tid)
    if row(c, 'SELECT 1 FROM slots WHERE term_id=? UNION SELECT 1 FROM invoices WHERE term_id=?', tid, tid):
        raise Invalid('Only a term with no slots and no invoices can be deleted.')
    c.execute('DELETE FROM terms WHERE id=?', (tid,))
    audit(c, actor, 'delete', 'terms', tid, t, None)


# ---------------------------------------------------------------- timetable

def slot_pupils(c, sid):
    return rows(c, '''SELECT p.* FROM slot_pupils sp JOIN pupils p ON p.id=sp.pupil_id
                      WHERE sp.slot_id=? ORDER BY p.name''', sid)


def slots_full(c, tid, **filters):
    sql = '''SELECT s.*, lt.name type_name, lt.price, t.name teacher_name, t.colour, r.name room_name
             FROM slots s JOIN lesson_types lt ON lt.id=s.lesson_type_id JOIN teachers t ON t.id=s.teacher_id
             JOIN rooms r ON r.id=s.room_id WHERE s.term_id=?'''
    args = [tid]
    for k in ('room_id', 'teacher_id', 'weekday'):
        if filters.get(k) not in (None, ''):
            sql += f' AND s.{k}=?'
            args.append(int(filters[k]))
    if filters.get('pupil_id'):
        sql += ' AND s.id IN (SELECT slot_id FROM slot_pupils WHERE pupil_id=?)'
        args.append(int(filters['pupil_id']))
    out = []
    for s in rows(c, sql + ' ORDER BY s.weekday, s.start_min, r.name', *args):
        s = dict(s)
        s['pupils'] = [dict(p) for p in slot_pupils(c, s['id'])]
        s['end_min'] = s['start_min'] + s['duration']
        s['label'] = (f"{s['type_name']} ({s['teacher_name']}" +
                      ''.join(', ' + p['name'] for p in s['pupils']) + ')')
        out.append(s)
    return out


def _validate_slot(c, tid, f, existing=None):
    t = term(c, tid)
    if t['closed']:
        raise Invalid('This term is closed.')
    errors = {}
    wd = parse_int(f.get('weekday'), 'weekday', errors, 0, 6, 'a weekday')
    start = parse_time(f.get('start'), 'start', errors)

    def pick(table, field, label):
        v = str(f.get(field) or '')
        r = row(c, f'SELECT * FROM {table} WHERE id=?', v) if v.isdigit() else None
        if not r:
            errors[field] = f'Choose a {label}.'
        elif r['archived'] and not (existing and existing.get(field) == r['id']):
            errors[field] = f'{r["name"]} is archived.'
        return r

    lt = pick('lesson_types', 'lesson_type_id', 'lesson type')
    pick('teachers', 'teacher_id', 'teacher')
    pick('rooms', 'room_id', 'room')
    pids = sorted({int(p) for p in (f.get('pupils') or []) if str(p).isdigit()})
    old_pids = {p['id'] for p in slot_pupils(c, existing['id'])} if existing else set()
    for pid in pids:
        p = row(c, 'SELECT * FROM pupils WHERE id=?', pid)
        if not p:
            errors['pupils'] = 'Unknown pupil.'
        elif p['archived'] and pid not in old_pids:
            errors['pupils'] = f'{p["name"]} is archived.'
    if lt and len(pids) > lt['max_pupils']:
        errors['pupils'] = f'{lt["name"]} allows at most {lt["max_pupils"]} pupil(s); {len(pids)} chosen.'
    sd = parse_date(f.get('start_date') or t['first_day'], 'start_date', errors)
    ed = parse_date(f.get('end_date') or t['last_day'], 'end_date', errors)
    if sd and ed:
        if ed < sd:
            errors['end_date'] = 'The end date is before the start date.'
        elif sd < d(t['first_day']) or ed > d(t['last_day']):
            errors['start_date'] = f'Dates must be within the term ({t["first_day"]} to {t["last_day"]}).'
    if start is not None and lt:
        o, cl = parse_time(setting(c, 'hours.open'), 'x', {}), parse_time(setting(c, 'hours.close'), 'x', {})
        if setting(c, 'timetable.end_within_hours') == 'start_only':
            if start < o or start >= cl:
                errors['start'] = (f'Outside opening hours ({setting(c, "hours.open")}–{setting(c, "hours.close")}):'
                                   f' this lesson would start at {hm(start)}.')
        elif start < o or start + lt['duration'] > cl:
            errors['start'] = (f'Outside opening hours ({setting(c, "hours.open")}–{setting(c, "hours.close")}): '
                               f'this lesson would run {hm(start)}–{hm(start + lt["duration"])}.')
    if errors:
        raise Invalid(errors)
    return {'term_id': tid, 'weekday': wd, 'start_min': start, 'duration': lt['duration'],
            'lesson_type_id': lt['id'], 'teacher_id': int(f['teacher_id']), 'room_id': int(f['room_id']),
            'start_date': sd.isoformat(), 'end_date': ed.isoformat(), 'pupils': pids}


def find_conflicts(c, s, exclude_id=None):
    """One message per clash between candidate slot s and existing slots in the same term."""
    msgs = []
    others = rows(c, '''SELECT s.*, lt.name type_name, t.name teacher_name, r.name room_name FROM slots s
        JOIN lesson_types lt ON lt.id=s.lesson_type_id JOIN teachers t ON t.id=s.teacher_id
        JOIN rooms r ON r.id=s.room_id
        WHERE s.term_id=? AND s.weekday=? AND s.start_min < ? AND s.start_min + s.duration > ?
          AND s.start_date <= ? AND s.end_date >= ? AND s.id IS NOT ?''',
                  s['term_id'], s['weekday'], s['start_min'] + s['duration'], s['start_min'],
                  s['end_date'], s['start_date'], exclude_id)
    for o in others:
        ps = slot_pupils(c, o['id'])
        when = f"{DAYS[o['weekday']]} {hm(o['start_min'])}–{hm(o['start_min'] + o['duration'])}"
        who = ', '.join([o['teacher_name']] + [p['name'] for p in ps])
        dates = '' if (o['start_date'], o['end_date']) == (s['start_date'], s['end_date']) else \
            f" from {o['start_date']} to {o['end_date']}"
        if o['room_id'] == s['room_id']:
            msgs.append(f"{o['room_name']} is booked {when} by {o['type_name']} ({who}){dates}.")
        if o['teacher_id'] == s['teacher_id']:
            msgs.append(f"{o['teacher_name']} is teaching {when}: {o['type_name']} in {o['room_name']}{dates}.")
        for p in ps:
            if p['id'] in s['pupils']:
                msgs.append(f"{p['name']} already has {o['type_name']} {when} with {o['teacher_name']} in "
                            f"{o['room_name']}{dates}.")
    return msgs


def invoiced_until(c, sid):
    """Last lesson date of this slot that appears on an issued (non-void) invoice, or None."""
    last = None
    for r in rows(c, '''SELECT l.dates FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id
                        WHERE l.slot_id=? AND i.status='issued' ''', sid):
        for x in r['dates'].split(','):
            if x and (last is None or x > last):
                last = x
    # An issued invoice covers the whole term even when the slot had no chargeable dates on it.
    return d(last) if last else None


def _save_slot_pupils(c, sid, pids):
    c.execute('DELETE FROM slot_pupils WHERE slot_id=?', (sid,))
    c.executemany('INSERT INTO slot_pupils VALUES (?,?)', [(sid, p) for p in pids])


def create_slot(c, actor, tid, f):
    s = _validate_slot(c, tid, f)
    clashes = find_conflicts(c, s)
    if clashes:
        raise Invalid({'_': clashes})
    cur = c.execute('''INSERT INTO slots(term_id,weekday,start_min,duration,lesson_type_id,teacher_id,room_id,
                       start_date,end_date) VALUES (?,?,?,?,?,?,?,?,?)''',
                    (tid, s['weekday'], s['start_min'], s['duration'], s['lesson_type_id'], s['teacher_id'],
                     s['room_id'], s['start_date'], s['end_date']))
    _save_slot_pupils(c, cur.lastrowid, s['pupils'])
    audit(c, actor, 'create', 'slots', cur.lastrowid, None, s)
    return cur.lastrowid


def get_slot(c, sid):
    s = as_dict(row(c, 'SELECT * FROM slots WHERE id=?', sid))
    if not s:
        raise Invalid('No such slot.')
    s['pupils'] = [p['id'] for p in slot_pupils(c, sid)]
    return s


def update_slot(c, actor, sid, f, version=None):
    old = get_slot(c, sid)
    s = _validate_slot(c, old['term_id'], f, existing=old)
    inv = invoiced_until(c, sid)
    if inv is not None:
        changed = any(old[k] != s[k] for k in ('weekday', 'start_min', 'duration', 'lesson_type_id', 'teacher_id',
                                                'room_id', 'start_date', 'pupils'))
        if changed or d(s['end_date']) <= inv:
            raise Invalid(f'Lessons up to {inv} are on an issued invoice. Issue a credit note instead, or end '
                          f'the slot from a date after {inv}.')
    clashes = find_conflicts(c, s, exclude_id=sid)
    if clashes:
        raise Invalid({'_': clashes})
    cur = c.execute('''UPDATE slots SET weekday=?,start_min=?,duration=?,lesson_type_id=?,teacher_id=?,room_id=?,
                       start_date=?,end_date=?,version=version+1 WHERE id=? AND version=?''',
                    (s['weekday'], s['start_min'], s['duration'], s['lesson_type_id'], s['teacher_id'],
                     s['room_id'], s['start_date'], s['end_date'], sid, int(version or old['version'])))
    if cur.rowcount == 0:
        raise Invalid('This record changed since you opened it. The newer values are shown below.', current=old)
    _save_slot_pupils(c, sid, s['pupils'])
    audit(c, actor, 'update', 'slots', sid, old, s)


def end_slot(c, actor, sid, from_date):
    """Stop a slot so that from_date and later have no lessons."""
    old = get_slot(c, sid)
    errors = {}
    fd = parse_date(from_date, 'from_date', errors)
    if errors:
        raise Invalid(errors)
    if fd <= d(old['start_date']):
        raise Invalid({'from_date': 'That is on or before the slot starts; delete the slot instead.'})
    if fd > d(old['end_date']):
        raise Invalid({'from_date': 'The slot already ends before that date.'})
    inv = invoiced_until(c, sid)
    if inv is not None and fd <= inv:
        raise Invalid(f'Lessons up to {inv} are on an issued invoice. Issue a credit note instead.')
    new_end = (fd - dt.timedelta(days=1)).isoformat()
    c.execute('UPDATE slots SET end_date=?, version=version+1 WHERE id=?', (new_end, sid))
    c.execute('DELETE FROM occurrence_status WHERE slot_id=? AND date>?', (sid, new_end))
    audit(c, actor, 'end', 'slots', sid, {'end_date': old['end_date']}, {'end_date': new_end})


def delete_slot(c, actor, sid):
    old = get_slot(c, sid)
    if row(c, '''SELECT 1 FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id
                 WHERE l.slot_id=? AND i.status<>'draft' ''', sid):
        raise Invalid('This slot has lessons on an issued invoice. End it from a later date instead.')
    c.execute('UPDATE invoice_lines SET slot_id=NULL WHERE slot_id=?', (sid,))
    c.execute('DELETE FROM slots WHERE id=?', (sid,))
    audit(c, actor, 'delete', 'slots', sid, old, None)


def copy_timetable(c, actor, src_tid, dst_tid):
    """Copy every slot of src term into dst term. Returns (created count, [(description, reasons)])."""
    src, dst = term(c, src_tid), term(c, dst_tid)
    if src_tid == dst_tid:
        raise Invalid('Choose a different term to copy from.')
    keep_pupils = setting(c, 'timetable.copy_pupils') == 'copy'
    created, skipped_list = 0, []
    for s in rows(c, 'SELECT * FROM slots WHERE term_id=? ORDER BY weekday, start_min', src_tid):
        pupils = [p['id'] for p in slot_pupils(c, s['id']) if not p['archived']] if keep_pupils else []
        f = {'weekday': s['weekday'], 'start': hm(s['start_min']), 'lesson_type_id': s['lesson_type_id'],
             'teacher_id': s['teacher_id'], 'room_id': s['room_id'], 'pupils': pupils,
             'start_date': dst['first_day'], 'end_date': dst['last_day']}
        c.execute('SAVEPOINT copy_one')
        try:
            create_slot(c, actor, dst_tid, f)
            created += 1
            c.execute('RELEASE copy_one')
        except Invalid as e:
            c.execute('ROLLBACK TO copy_one')
            c.execute('RELEASE copy_one')
            reasons = [m for v in e.errors.values() for m in ([v] if isinstance(v, str) else v)]
            skipped_list.append((describe_slot(c, s), reasons))
    audit(c, actor, 'copy_timetable', 'terms', dst_tid, {'from_term': src['name']},
          {'created': created, 'skipped': len(skipped_list)})
    return created, skipped_list


# ---------------------------------------------------------------- occurrences

def slot_dates(t, s, skip):
    """A slot's occurrences: its weekday's dates within the term and its own range, minus skipped dates."""
    start = max(d(t['first_day']), d(s['start_date']))
    end = min(d(t['last_day']), d(s['end_date']))
    x = start + dt.timedelta(days=(s['weekday'] - start.weekday()) % 7)
    out = []
    while x <= end:
        if x not in skip:
            out.append(x)
        x += dt.timedelta(days=7)
    return out


def statuses(c, sid):
    """{(date_iso, pupil_id): row}; pupil_id 0 means the whole lesson."""
    return {(r['date'], r['pupil_id']): r for r in rows(c, 'SELECT * FROM occurrence_status WHERE slot_id=?', sid)}


def chargeable_dates(c, t, s, pupil_id, skip, absent_charged):
    st = statuses(c, s['id'])
    out = []
    for x in slot_dates(t, s, skip):
        k = x.isoformat()
        if (k, 0) in st:
            continue
        if (k, pupil_id) in st and not absent_charged:
            continue
        out.append(x)
    return out


def list_occurrences(c, tid, **filters):
    t = term(c, tid)
    skip = skipped_dates(c, tid)
    out = []
    df, dto = filters.get('date_from'), filters.get('date_to')
    for s in slots_full(c, tid, **filters):
        st = statuses(c, s['id'])
        for x in slot_dates(t, s, skip):
            k = x.isoformat()
            if df and k < df or dto and k > dto:
                continue
            cancelled = st.get((k, 0))
            absent = [(p, st[(k, p['id'])]) for p in s['pupils'] if (k, p['id']) in st]
            out.append({'date': k, 'slot': s, 'cancelled': cancelled, 'absent': absent})
    out.sort(key=lambda o: (o['date'], o['slot']['start_min'], o['slot']['room_name']))
    return out


def _occurrence_invoiced(c, sid, date_iso):
    for r in rows(c, '''SELECT l.dates FROM invoice_lines l JOIN invoices i ON i.id=l.invoice_id
                        WHERE l.slot_id=? AND i.status='issued' ''', sid):
        if date_iso in r['dates'].split(','):
            return True
    # an issued invoice for the family covers this term even if this date was not charged
    return row(c, '''SELECT 1 FROM slot_pupils sp JOIN pupils p ON p.id=sp.pupil_id JOIN slots s ON s.id=sp.slot_id
                     JOIN invoices i ON i.family_id=p.family_id AND i.term_id=s.term_id
                     WHERE sp.slot_id=? AND i.status='issued' ''', sid) is not None


def set_occurrence(c, actor, sid, date_iso, action, reason='', pupil_id=None):
    s = get_slot(c, sid)
    t = term(c, s['term_id'])
    try:
        x = d(date_iso)
    except (ValueError, TypeError):
        raise Invalid('No such lesson.')
    if x not in slot_dates(t, s, skipped_dates(c, t['id'])):
        raise Invalid(f'There is no lesson on {date_iso} for this slot (skipped date or outside its range).')
    if _occurrence_invoiced(c, sid, x.isoformat()):
        raise Invalid('This lesson is on an issued invoice. Issue a credit note instead.')
    reason = (reason or '').strip()
    before = {f'{k[0]}/{k[1]}': r['status'] for k, r in statuses(c, sid).items() if k[0] == x.isoformat()}
    if action == 'cancel':
        if not reason:
            raise Invalid({'reason': 'Enter a reason for the cancellation.'})
        c.execute('DELETE FROM occurrence_status WHERE slot_id=? AND date=?', (sid, x.isoformat()))
        c.execute('INSERT INTO occurrence_status VALUES (?,?,0,?,?,?,?)',
                  (sid, x.isoformat(), 'cancelled', reason, actor['id'] if actor else None, now_iso()))
    elif action == 'absent':
        pids = s['pupils']
        if pupil_id in (None, '') and len(pids) == 1:
            pupil_id = pids[0]
        if not str(pupil_id).isdigit() or int(pupil_id) not in pids:
            raise Invalid({'pupil_id': 'Choose which pupil was absent.'})
        if (x.isoformat(), 0) in statuses(c, sid):
            raise Invalid('This lesson was cancelled by the school; restore it first.')
        c.execute('INSERT OR REPLACE INTO occurrence_status VALUES (?,?,?,?,?,?,?)',
                  (sid, x.isoformat(), int(pupil_id), 'absent', reason, actor['id'] if actor else None, now_iso()))
    elif action == 'restore':
        c.execute('DELETE FROM occurrence_status WHERE slot_id=? AND date=?', (sid, x.isoformat()))
    else:
        raise Invalid('Unknown action.')
    after = {f'{k[0]}/{k[1]}': r['status'] for k, r in statuses(c, sid).items() if k[0] == x.isoformat()}
    audit(c, actor, 'lesson_' + action, 'slots', sid, {'date': x.isoformat(), 'status': before},
          {'date': x.isoformat(), 'status': after, 'reason': reason})


# ---------------------------------------------------------------- invoices

def compute_lines(c, tid):
    """{family_id: [line dicts]} of chargeable lesson lines for the term."""
    t = term(c, tid)
    skip = skipped_dates(c, tid)
    absent_charged = setting(c, 'billing.pupil_absence') == 'charge'
    sym = currency_symbol(c)
    out = {}
    for s in slots_full(c, tid):
        for p in s['pupils']:
            dates = chargeable_dates(c, t, s, p['id'], skip, absent_charged)
            if not dates:
                continue
            n = len(dates)
            amount = n * s['price']
            desc = (f"{p['name']} – {s['type_name']} – {DAYS[s['weekday']]} {hm(s['start_min'])} – "
                    f"{n} lesson{'s' if n != 1 else ''} × {money(s['price'], sym)} = {money(amount, sym)}")
            out.setdefault(p['family_id'], []).append({
                'kind': 'lesson', 'pupil_id': p['id'], 'slot_id': s['id'], 'description': desc,
                'quantity': n, 'unit_price': s['price'], 'amount': amount,
                'dates': ','.join(x.isoformat() for x in dates)})
    return out


def _insert_lines(c, inv_id, lines):
    for ln in lines:
        c.execute('''INSERT INTO invoice_lines(invoice_id,kind,pupil_id,slot_id,description,quantity,unit_price,
                     amount,dates) VALUES (?,?,?,?,?,?,?,?,?)''',
                  (inv_id, ln['kind'], ln['pupil_id'], ln['slot_id'], ln['description'], ln['quantity'],
                   ln['unit_price'], ln['amount'], ln['dates']))


def generate_drafts(c, actor, tid):
    """One draft per family with chargeable lessons that has no non-void invoice. Safe to repeat."""
    t = term(c, tid)
    if t['closed']:
        raise Invalid('This term is closed.')
    made = 0
    for fam_id, lines in compute_lines(c, tid).items():
        if row(c, "SELECT 1 FROM invoices WHERE term_id=? AND family_id=? AND status<>'void'", tid, fam_id):
            continue
        cur = c.execute("INSERT INTO invoices(term_id,family_id,status,created_at) VALUES (?,?,'draft',?)",
                        (tid, fam_id, now_iso()))
        _insert_lines(c, cur.lastrowid, lines)
        made += 1
        audit(c, actor, 'generate', 'invoices', cur.lastrowid, None,
              {'family_id': fam_id, 'term_id': tid, 'total': sum(x['amount'] for x in lines)})
    return made


def regenerate(c, actor, tid, invoice_id=None):
    """Rebuild lesson lines of drafts from the current timetable, keeping manual adjustments."""
    computed = compute_lines(c, tid)
    sql = "SELECT * FROM invoices WHERE term_id=? AND status='draft'"
    args = [tid]
    if invoice_id:
        sql += ' AND id=?'
        args.append(invoice_id)
    n = 0
    for inv in rows(c, sql, *args):
        before = invoice_figures(c, inv)['total']
        c.execute("DELETE FROM invoice_lines WHERE invoice_id=? AND kind='lesson'", (inv['id'],))
        _insert_lines(c, inv['id'], computed.get(inv['family_id'], []))
        audit(c, actor, 'regenerate', 'invoices', inv['id'], {'total': before},
              {'total': invoice_figures(c, inv)['total']})
        n += 1
    return n


def get_invoice(c, iid):
    inv = as_dict(row(c, '''SELECT i.*, f.name family_name, f.address family_address, f.email family_email,
                            t.name term_name FROM invoices i JOIN families f ON f.id=i.family_id
                            JOIN terms t ON t.id=i.term_id WHERE i.id=?''', iid))
    if not inv:
        raise Invalid('No such invoice.')
    return inv


def _draft(c, iid):
    inv = get_invoice(c, iid)
    if inv['status'] != 'draft':
        raise Invalid('Only a draft can be changed. Issue a credit note instead.')
    return inv


def add_adjustment(c, actor, iid, f):
    _draft(c, iid)
    errors = {}
    desc = (f.get('description') or '').strip()
    if not desc:
        errors['description'] = 'Enter a description, e.g. "Sibling discount".'
    amt = parse_money(f.get('amount'), 'amount', errors, allow_negative=True)
    if errors:
        raise Invalid(errors)
    _insert_lines(c, iid, [{'kind': 'adjustment', 'pupil_id': None, 'slot_id': None, 'description': desc,
                            'quantity': 1, 'unit_price': amt, 'amount': amt, 'dates': ''}])
    audit(c, actor, 'add_adjustment', 'invoices', iid, None, {'description': desc, 'amount': amt})


def remove_adjustment(c, actor, line_id):
    ln = row(c, "SELECT * FROM invoice_lines WHERE id=? AND kind='adjustment'", line_id)
    if not ln:
        raise Invalid('No such adjustment.')
    _draft(c, ln['invoice_id'])
    c.execute('DELETE FROM invoice_lines WHERE id=?', (line_id,))
    audit(c, actor, 'remove_adjustment', 'invoices', ln['invoice_id'], dict(ln), None)


def issue(c, actor, iid, issue_date=None):
    inv = _draft(c, iid)
    total = invoice_figures(c, inv)['total']
    if total <= 0:
        raise Invalid(f'Invoice for {inv["family_name"]} has a total of {money(total, currency_symbol(c))}; '
                      'only invoices above zero can be issued.')
    idate = d(issue_date) if issue_date else today(c)
    if setting(c, 'invoices.number_year') == 'term_start':
        year = d(term(c, inv['term_id'])['first_day']).year
    else:
        year = idate.year
    r = row(c, 'SELECT last FROM invoice_seq WHERE year=?', year)
    n = (r['last'] if r else 0) + 1
    c.execute('INSERT INTO invoice_seq(year,last) VALUES (?,?) ON CONFLICT(year) DO UPDATE SET last=excluded.last',
              (year, n))
    number = f'{year}-{n:04d}'
    due = idate + dt.timedelta(days=int(setting(c, 'invoices.due_days')))
    c.execute("UPDATE invoices SET status='issued', number=?, issue_date=?, due_date=? WHERE id=?",
              (number, idate.isoformat(), due.isoformat(), iid))
    audit(c, actor, 'issue', 'invoices', iid, {'status': 'draft'},
          {'status': 'issued', 'number': number, 'issue_date': idate, 'due_date': due, 'total': total})
    # apply any family credit held from earlier overpayments
    credit = family_credit(c, inv['family_id'])
    if credit > 0:
        use = min(credit, total)
        _entry(c, actor, None, inv['family_id'], 'family_credit', -use, idate.isoformat(),
               reason=f'Applied to invoice {number}')
        _entry(c, actor, iid, inv['family_id'], 'credit_applied', use, idate.isoformat(), method='family credit',
               reason='Family credit from an earlier overpayment')
    return number


def issue_all(c, actor, tid):
    ids = [r['id'] for r in rows(c, "SELECT id FROM invoices WHERE term_id=? AND status='draft' ORDER BY id", tid)]
    issued, refused = 0, []
    for iid in ids:
        try:
            c.execute('SAVEPOINT issue_one')
            issue(c, actor, iid)
            c.execute('RELEASE issue_one')
            issued += 1
        except Invalid as e:
            c.execute('ROLLBACK TO issue_one')
            c.execute('RELEASE issue_one')
            refused.append(str(e))
    return issued, refused


def invoice_lines(c, iid):
    return rows(c, 'SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY kind DESC, id', iid)


def invoice_figures(c, inv):
    iid = inv['id']
    total = row(c, 'SELECT COALESCE(SUM(amount),0) s FROM invoice_lines WHERE invoice_id=?', iid)['s']
    credited = row(c, 'SELECT COALESCE(SUM(amount),0) s FROM credit_notes WHERE invoice_id=?', iid)['s']
    sums = {r['kind']: r['s'] for r in rows(c, '''SELECT kind, SUM(amount) s FROM entries WHERE invoice_id=?
                                                  GROUP BY kind''', iid)}
    paid = sums.get('payment', 0) + sums.get('credit_applied', 0)
    reversed_ = -sums.get('reversal', 0)
    refunded = -sums.get('refund', 0)
    balance = total - credited - paid + reversed_ + refunded
    if inv['status'] in ('draft', 'void'):
        status = inv['status']
    elif balance <= 0:
        status = 'paid'
    elif balance == total:
        status = 'issued'
    else:
        status = 'part-paid'
    overdue = (status in ('issued', 'part-paid') and inv['due_date'] is not None
               and today(c) > d(inv['due_date']) and balance > 0)
    return {'total': total, 'credited': credited, 'paid': paid - reversed_, 'payments': paid,
            'reversed': reversed_, 'refunded': refunded, 'balance': balance, 'status': status,
            'overdue': overdue, 'overpaid': max(0, -balance)}


def list_invoices(c, tid=None, family_id=None):
    sql = '''SELECT i.*, f.name family_name, t.name term_name,
             (SELECT COUNT(*) FROM invoice_lines l WHERE l.invoice_id=i.id) n_lines
             FROM invoices i JOIN families f ON f.id=i.family_id JOIN terms t ON t.id=i.term_id WHERE 1=1'''
    args = []
    if tid:
        sql += ' AND i.term_id=?'
        args.append(tid)
    if family_id:
        sql += ' AND i.family_id=?'
        args.append(family_id)
    out = []
    for r in rows(c, sql + ' ORDER BY t.first_day DESC, f.name COLLATE NOCASE, i.id', *args):
        r = dict(r)
        r.update(invoice_figures(c, r))
        out.append(r)
    return out


def credit_note(c, actor, iid, f):
    """f: reason and lines text, one 'description | amount' per line (or description + amount fields)."""
    inv = get_invoice(c, iid)
    if inv['status'] != 'issued':
        raise Invalid('Credit notes can only be raised against an issued invoice.')
    errors = {}
    reason = (f.get('reason') or '').strip()
    if not reason:
        errors['reason'] = 'Enter a reason.'
    lines = []
    text = (f.get('lines') or '').strip()
    if not text and f.get('amount'):
        text = f"{f.get('description') or reason} | {f['amount']}"
    for ln in text.splitlines():
        if not ln.strip():
            continue
        desc, _, amt = ln.rpartition('|')
        e = {}
        cents = parse_money(amt, 'x', e)
        if e or not desc.strip():
            errors['lines'] = f'Line "{ln.strip()}" should look like: Cancelled lesson 14 Oct | 21.00'
            break
        lines.append({'description': desc.strip(), 'amount': cents})
    if not lines and 'lines' not in errors:
        errors['lines'] = 'Enter at least one line.'
    if errors:
        raise Invalid(errors)
    amount = sum(x['amount'] for x in lines)
    fig = invoice_figures(c, inv)
    remaining = fig['total'] - fig['credited']
    if amount > remaining:
        raise Invalid({'lines': f'The credit ({money(amount, currency_symbol(c))}) is larger than the remaining '
                                f'invoice total ({money(remaining, currency_symbol(c))}).'})
    cur = c.execute('INSERT INTO credit_notes(invoice_id,amount,reason,lines,user_id,created_at) VALUES (?,?,?,?,?,?)',
                    (iid, amount, reason, json.dumps(lines), actor['id'] if actor else None, now_iso()))
    audit(c, actor, 'credit_note', 'invoices', iid, {'balance': fig['balance']},
          {'credit_note': cur.lastrowid, 'amount': amount, 'reason': reason, 'lines': lines})
    return cur.lastrowid


def void_invoice(c, actor, iid, reason):
    if actor is not None and actor['role'] != 'admin' and setting(c, 'invoices.void_permission') == 'admin_only':
        raise Forbidden('Only an admin can void invoices.')
    inv = get_invoice(c, iid)
    if inv['status'] == 'void':
        raise Invalid('This invoice is already void.')
    if not (reason or '').strip():
        raise Invalid({'reason': 'Enter a reason.'})
    net = row(c, 'SELECT COALESCE(SUM(amount),0) s FROM entries WHERE invoice_id=?', iid)['s']
    if net != 0:
        raise Invalid('This invoice has payments. Reverse or refund them before voiding.')
    if inv['status'] == 'draft':
        # a draft holds no number; discarding it is the same as voiding
        pass
    c.execute("UPDATE invoices SET status='void', void_reason=? WHERE id=?", (reason.strip(), iid))
    audit(c, actor, 'void', 'invoices', iid, {'status': inv['status']}, {'status': 'void', 'reason': reason.strip()})


# ---------------------------------------------------------------- payments

def _entry(c, actor, iid, fam_id, kind, amount, date_iso, method='', reference='', reason='', ref_entry_id=None):
    cur = c.execute('''INSERT INTO entries(invoice_id,family_id,kind,amount,date,method,reference,reason,ref_entry_id,
                       user_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (iid, fam_id, kind, amount, date_iso, method, reference, reason, ref_entry_id,
                     actor['id'] if actor else None, now_iso()))
    audit(c, actor, kind, 'invoices' if iid else 'families', iid or fam_id, None,
          {'entry': cur.lastrowid, 'amount': amount, 'date': date_iso, 'method': method, 'reference': reference,
           'reason': reason})
    return cur.lastrowid


def family_credit(c, fam_id):
    return row(c, "SELECT COALESCE(SUM(amount),0) s FROM entries WHERE family_id=? AND kind='family_credit'",
               fam_id)['s']


def _money_inputs(c, f, need_method=True):
    errors = {}
    amount = parse_money(f.get('amount'), 'amount', errors)
    when = parse_date(f.get('date') or today(c).isoformat(), 'date', errors)
    if when and when > today(c):
        errors['date'] = 'The date cannot be in the future.'
    method = (f.get('method') or '').strip()
    if need_method and method not in METHODS:
        errors['method'] = 'Choose a method.'
    return amount, when, method, errors


def record_payment(c, actor, iid, f):
    """Re-checks the balance inside the caller's transaction, so concurrent payments cannot overpay."""
    inv = get_invoice(c, iid)
    amount, when, method, errors = _money_inputs(c, f)
    if errors:
        raise Invalid(errors)
    if inv['status'] != 'issued':
        raise Invalid('Payments can only be recorded against an issued invoice.')
    if setting(c, 'payments.before_issue_date') == 'refused' and when < d(inv['issue_date']):
        raise Invalid({'date': f'The payment date cannot be before the invoice was issued ({inv["issue_date"]}).'})
    bal = invoice_figures(c, inv)['balance']
    ref = (f.get('reference') or '').strip()
    excess = amount - max(bal, 0)
    if excess > 0:
        if setting(c, 'payments.overpayment') == 'reject':
            raise Invalid({'amount': f'That is more than the balance of {money(bal, currency_symbol(c))}.'})
        on_invoice = amount - excess
        pid = None
        if on_invoice > 0:
            pid = _entry(c, actor, iid, inv['family_id'], 'payment', on_invoice, when.isoformat(), method, ref)
        _entry(c, actor, None, inv['family_id'], 'family_credit', excess, when.isoformat(), method, ref,
               reason=f'Overpayment on invoice {inv["number"]}', ref_entry_id=pid)
        return pid
    return _entry(c, actor, iid, inv['family_id'], 'payment', amount, when.isoformat(), method, ref)


def mark_paid(c, actor, iid, method):
    inv = get_invoice(c, iid)
    bal = invoice_figures(c, inv)['balance']
    if inv['status'] != 'issued':
        raise Invalid('Payments can only be recorded against an issued invoice.')
    if bal <= 0:
        raise Invalid('This invoice has nothing left to pay.')
    return record_payment(c, actor, iid, {'amount': f'{bal / 100:.2f}', 'method': method,
                                          'date': today(c).isoformat()})


def reverse_payment(c, actor, entry_id, reason):
    e = row(c, "SELECT * FROM entries WHERE id=? AND kind='payment'", entry_id)
    if not e:
        raise Invalid('No such payment.')
    if not (reason or '').strip():
        raise Invalid({'reason': 'Enter a reason.'})
    if row(c, "SELECT 1 FROM entries WHERE ref_entry_id=? AND kind='reversal'", entry_id):
        raise Invalid('This payment has already been reversed.')
    return _entry(c, actor, e['invoice_id'], e['family_id'], 'reversal', -e['amount'], today(c).isoformat(),
                  e['method'], e['reference'], reason.strip(), ref_entry_id=entry_id)


def refund(c, actor, iid, f):
    inv = get_invoice(c, iid)
    amount, when, method, errors = _money_inputs(c, f)
    if errors:
        raise Invalid(errors)
    if inv['status'] != 'issued':
        raise Invalid('Refunds can only be recorded against an issued invoice.')
    over = invoice_figures(c, inv)['overpaid']
    if amount > over:
        raise Invalid({'amount': f'You can refund at most the overpaid amount '
                                 f'({money(over, currency_symbol(c))}).'})
    return _entry(c, actor, iid, inv['family_id'], 'refund', -amount, when.isoformat(), method,
                  (f.get('reference') or '').strip(), (f.get('reason') or '').strip())


def invoice_entries(c, iid):
    return rows(c, '''SELECT e.*, u.username, (SELECT 1 FROM entries r WHERE r.ref_entry_id=e.id AND r.kind='reversal')
                      reversed FROM entries e LEFT JOIN users u ON u.id=e.user_id WHERE e.invoice_id=?
                      ORDER BY e.id''', iid)


# ---------------------------------------------------------------- reports

def term_report(c, tid):
    term(c, tid)
    fams = {}
    overdue = 0
    for inv in list_invoices(c, tid=tid):
        if inv['status'] in ('draft', 'void'):
            continue
        r = fams.setdefault(inv['family_id'], {'family': inv['family_name'], 'invoiced': 0, 'credited': 0,
                                               'paid': 0, 'refunded': 0, 'outstanding': 0, 'invoices': []})
        r['invoiced'] += inv['total']
        r['credited'] += inv['credited']
        r['paid'] += inv['paid']
        r['refunded'] += inv['refunded']
        r['outstanding'] += inv['balance']
        r['invoices'].append(inv['number'])
        overdue += inv['overdue']
    out = sorted(fams.values(), key=lambda r: r['family'].lower())
    totals = {k: sum(r[k] for r in out) for k in ('invoiced', 'credited', 'paid', 'refunded', 'outstanding')}
    return out, totals, overdue


def parse_range(c, f):
    errors = {}
    t = today(c)
    start = parse_date(f.get('start') or t.replace(day=1).isoformat(), 'start', errors)
    end = parse_date(f.get('end') or t.isoformat(), 'end', errors)
    if start and end:
        if end < start:
            errors['end'] = 'The range ends before it starts.'
        elif (end - start).days + 1 > 366:
            errors['end'] = 'The range cannot be longer than 366 days.'
    if errors:
        raise Invalid(errors)
    return start, end


def payments_report(c, start, end):
    es = rows(c, '''SELECT e.*, f.name family_name, i.number FROM entries e JOIN families f ON f.id=e.family_id
                    LEFT JOIN invoices i ON i.id=e.invoice_id
                    WHERE e.date BETWEEN ? AND ? AND e.kind IN ('payment','reversal','refund')
                    ORDER BY e.date, e.id''', start.isoformat(), end.isoformat())
    by_method, by_day = {}, {}
    for e in es:
        by_method[e['method']] = by_method.get(e['method'], 0) + e['amount']
        by_day[e['date']] = by_day.get(e['date'], 0) + e['amount']
    return es, by_method, by_day, sum(e['amount'] for e in es)


def teacher_report(c, tid):
    t = term(c, tid)
    skip = skipped_dates(c, tid)
    td = today(c)
    out = {}
    for s in slots_full(c, tid):
        r = out.setdefault(s['teacher_id'], {'teacher': s['teacher_name'], 'delivered': 0, 'cancelled': 0,
                                             'scheduled': 0})
        st = statuses(c, s['id'])
        for x in slot_dates(t, s, skip):
            if (x.isoformat(), 0) in st:
                r['cancelled'] += 1
            elif x <= td:
                r['delivered'] += 1
            else:
                r['scheduled'] += 1
    return sorted(out.values(), key=lambda r: r['teacher'].lower())


def audit_log(c, entity='', entity_id='', start='', end='', limit=500):
    sql = 'SELECT * FROM audit WHERE 1=1'
    args = []
    if entity:
        sql += ' AND entity=?'
        args.append(entity)
    if str(entity_id).isdigit():
        sql += ' AND entity_id=?'
        args.append(int(entity_id))
    if start:
        sql += ' AND at>=?'
        args.append(start)
    if end:
        sql += ' AND at<?'
        args.append((d(end) + dt.timedelta(days=1)).isoformat())
    return rows(c, sql + ' ORDER BY id DESC LIMIT ?', *args, limit)


def is_empty(c):
    return not any(row(c, f'SELECT 1 FROM {t}') for t in
                   ('teachers', 'rooms', 'lesson_types', 'families', 'pupils', 'terms', 'invoices'))
