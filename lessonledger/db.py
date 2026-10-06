"""Storage: configuration, connections, schema migrations, backup and restore."""
import configparser
import contextlib
import datetime
import glob
import logging
import os
import secrets
import shutil
import sqlite3

APP_ID = 'lesson-ledger'
log = logging.getLogger('lessonledger')


class BackupError(Exception):
    pass


def load_config(env=None):
    """Settings come from a config file (LL_CONFIG, default ./lessonledger.conf), then env vars."""
    env = os.environ if env is None else env
    cfg = {'host': '127.0.0.1', 'port': '8080', 'data_dir': 'data', 'backup_dir': '',
           'backup_keep': '14', 'log_level': 'INFO'}
    path = env.get('LL_CONFIG', 'lessonledger.conf')
    if os.path.exists(path):
        cp = configparser.ConfigParser()
        cp.read(path)
        if cp.has_section('lessonledger'):
            for k in cfg:
                if cp.has_option('lessonledger', k):
                    cfg[k] = cp.get('lessonledger', k)
    for k in cfg:
        if env.get('LL_' + k.upper()):
            cfg[k] = env['LL_' + k.upper()]
    cfg['port'] = int(cfg['port'])
    cfg['backup_keep'] = max(1, int(cfg['backup_keep']))
    cfg['data_dir'] = os.path.abspath(cfg['data_dir'])
    cfg['backup_dir'] = os.path.abspath(cfg['backup_dir'] or os.path.join(cfg['data_dir'], 'backups'))
    cfg['db_path'] = os.path.join(cfg['data_dir'], 'lessonledger.db')
    return cfg


def connect(path):
    c = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=FULL')
    c.execute('PRAGMA busy_timeout=30000')
    return c


@contextlib.contextmanager
def tx(c):
    """One write transaction. BEGIN IMMEDIATE serialises writers, so checks and saves are atomic."""
    c.execute('BEGIN IMMEDIATE')
    try:
        yield c
    except BaseException:
        c.execute('ROLLBACK')
        raise
    c.execute('COMMIT')


_IMMUTABLE = ''.join(
    f"""CREATE TRIGGER {t}_no_{op} BEFORE {op.upper()} ON {t}
        BEGIN SELECT RAISE(ABORT, '{t} entries are immutable'); END;\n"""
    for t in ('entries', 'credit_notes', 'audit') for op in ('update', 'delete'))

MIGRATIONS = [
    """
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff')),
        pw_hash TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
        failed INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        csrf TEXT NOT NULL, last_seen REAL NOT NULL);
    CREATE TABLE teachers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '', colour TEXT NOT NULL DEFAULT '#4a90d9',
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE rooms(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE lesson_types(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        duration INTEGER NOT NULL CHECK(duration BETWEEN 15 AND 120), price INTEGER NOT NULL CHECK(price > 0),
        max_pupils INTEGER NOT NULL DEFAULT 1 CHECK(max_pupils BETWEEN 1 AND 12),
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE families(id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE pupils(id INTEGER PRIMARY KEY, name TEXT NOT NULL, dob TEXT NOT NULL DEFAULT '',
        instrument TEXT NOT NULL DEFAULT '', family_id INTEGER NOT NULL REFERENCES families(id),
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE terms(id INTEGER PRIMARY KEY, name TEXT NOT NULL, first_day TEXT NOT NULL,
        last_day TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE skipped(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
        start TEXT NOT NULL, end TEXT NOT NULL, label TEXT NOT NULL);
    CREATE TABLE slots(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id),
        weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6), start_min INTEGER NOT NULL,
        duration INTEGER NOT NULL, lesson_type_id INTEGER NOT NULL REFERENCES lesson_types(id),
        teacher_id INTEGER NOT NULL REFERENCES teachers(id), room_id INTEGER NOT NULL REFERENCES rooms(id),
        start_date TEXT NOT NULL, end_date TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX slots_term ON slots(term_id, weekday);
    CREATE TABLE slot_pupils(slot_id INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
        pupil_id INTEGER NOT NULL REFERENCES pupils(id), PRIMARY KEY(slot_id, pupil_id));
    CREATE TABLE occurrence_status(slot_id INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
        date TEXT NOT NULL, pupil_id INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL CHECK(status IN ('cancelled','absent')), reason TEXT NOT NULL DEFAULT '',
        user_id INTEGER, at TEXT NOT NULL, PRIMARY KEY(slot_id, date, pupil_id));
    CREATE TABLE invoices(id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL REFERENCES terms(id),
        family_id INTEGER NOT NULL REFERENCES families(id),
        status TEXT NOT NULL CHECK(status IN ('draft','issued','void')), number TEXT UNIQUE,
        issue_date TEXT, due_date TEXT, void_reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    CREATE UNIQUE INDEX invoices_one_per_family ON invoices(term_id, family_id) WHERE status <> 'void';
    CREATE TABLE invoice_lines(id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        kind TEXT NOT NULL CHECK(kind IN ('lesson','adjustment')), pupil_id INTEGER, slot_id INTEGER,
        description TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1, unit_price INTEGER NOT NULL DEFAULT 0,
        amount INTEGER NOT NULL, dates TEXT NOT NULL DEFAULT '');
    CREATE TRIGGER lines_frozen_update BEFORE UPDATE ON invoice_lines
        WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'draft'
        BEGIN SELECT RAISE(ABORT, 'issued invoice lines are immutable'); END;
    CREATE TRIGGER lines_frozen_delete BEFORE DELETE ON invoice_lines
        WHEN (SELECT status FROM invoices WHERE id = OLD.invoice_id) <> 'draft'
        BEGIN SELECT RAISE(ABORT, 'issued invoice lines are immutable'); END;
    CREATE TABLE invoice_seq(year INTEGER PRIMARY KEY, last INTEGER NOT NULL);
    CREATE TABLE credit_notes(id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        amount INTEGER NOT NULL CHECK(amount > 0), reason TEXT NOT NULL, lines TEXT NOT NULL,
        user_id INTEGER, created_at TEXT NOT NULL);
    CREATE TABLE entries(id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id),
        family_id INTEGER NOT NULL REFERENCES families(id),
        kind TEXT NOT NULL CHECK(kind IN ('payment','reversal','refund','credit_applied','family_credit')),
        amount INTEGER NOT NULL, date TEXT NOT NULL, method TEXT NOT NULL DEFAULT '',
        reference TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', ref_entry_id INTEGER,
        user_id INTEGER, created_at TEXT NOT NULL);
    CREATE INDEX entries_invoice ON entries(invoice_id);
    CREATE INDEX entries_date ON entries(date);
    CREATE TABLE audit(id INTEGER PRIMARY KEY, at TEXT NOT NULL, user_id INTEGER, username TEXT NOT NULL,
        action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, before TEXT, after TEXT);
    CREATE INDEX audit_entity ON audit(entity, entity_id);
    CREATE INDEX audit_at ON audit(at);
    """ + _IMMUTABLE,
]
LATEST = len(MIGRATIONS)


def schema_version(c):
    return c.execute('PRAGMA user_version').fetchone()[0]


def open_db(cfg, backup=True):
    """Open the data store, creating it if needed and running pending migrations
    (after taking a backup of the existing data)."""
    os.makedirs(cfg['data_dir'], exist_ok=True)
    c = connect(cfg['db_path'])
    v = schema_version(c)
    if v > LATEST:
        raise BackupError(f'Data is from a newer version (schema {v}, this program supports {LATEST}).')
    if 0 < v < LATEST and backup:
        write_backup(c, cfg, prefix='pre-migration')
    migrate(c)
    return c


def migrate(c):
    v = schema_version(c)
    for i in range(v, LATEST):
        c.executescript('BEGIN;' + MIGRATIONS[i] + f'; PRAGMA user_version={i + 1}; COMMIT;')
        if i == 0:
            c.execute('INSERT INTO meta VALUES (?, ?)', ('app', APP_ID))
            c.execute('INSERT INTO meta VALUES (?, ?)', ('session_secret', secrets.token_hex(32)))
        log.info('Migrated schema to version %s', i + 1)


def backup_to(c, dest):
    tmp = dest + '.part'
    if os.path.exists(tmp):
        os.remove(tmp)
    dst = sqlite3.connect(tmp)
    with dst:
        c.backup(dst)
    dst.execute('PRAGMA journal_mode=DELETE')
    dst.close()
    os.replace(tmp, dest)
    return dest


def write_backup(c, cfg, prefix='auto'):
    os.makedirs(cfg['backup_dir'], exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path = backup_to(c, os.path.join(cfg['backup_dir'], f'lessonledger-{prefix}-{stamp}.db'))
    if prefix == 'auto':
        olds = sorted(glob.glob(os.path.join(cfg['backup_dir'], 'lessonledger-auto-*.db')))
        for old in olds[:-cfg['backup_keep']]:
            os.remove(old)
    return path


def check_backup(path):
    """Return the schema version of a valid backup file, or raise BackupError."""
    if not os.path.isfile(path):
        raise BackupError(f'No such file: {path}')
    try:
        src = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise BackupError('Backup file is corrupt.')
            row = src.execute("SELECT value FROM meta WHERE key='app'").fetchone()
            if not row or row[0] != APP_ID:
                raise BackupError('This is not a Lesson Ledger backup.')
            v = src.execute('PRAGMA user_version').fetchone()[0]
        finally:
            src.close()
    except sqlite3.DatabaseError as e:
        raise BackupError(f'Backup file is corrupt or not a Lesson Ledger backup ({e}).')
    if v > LATEST:
        raise BackupError(f'Backup is from a newer version (backup schema {v}, this program supports {LATEST}).')
    return v


def pid_running(cfg):
    pidfile = os.path.join(cfg['data_dir'], 'lessonledger.pid')
    try:
        pid = int(open(pidfile).read().strip())
        os.kill(pid, 0)
        return pid != os.getpid()
    except (OSError, ValueError):
        return False


def restore(cfg, path):
    """Replace the current data with a backup. Keeps a copy of the current data first."""
    check_backup(path)
    if pid_running(cfg):
        raise BackupError('The service is running. Stop it before restoring.')
    os.makedirs(cfg['data_dir'], exist_ok=True)
    kept = None
    if os.path.exists(cfg['db_path']):
        cur = connect(cfg['db_path'])
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        kept = backup_to(cur, os.path.join(cfg['data_dir'], f'pre-restore-{stamp}.db'))
        cur.close()
    tmp = cfg['db_path'] + '.restoring'
    shutil.copyfile(path, tmp)
    for suffix in ('-wal', '-shm'):
        if os.path.exists(cfg['db_path'] + suffix):
            os.remove(cfg['db_path'] + suffix)
    os.replace(tmp, cfg['db_path'])
    c = connect(cfg['db_path'])
    migrate(c)
    c.close()
    return kept
