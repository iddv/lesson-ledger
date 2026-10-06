"""HTTP server and HTML pages (standard library only)."""
import csv
import datetime as dt
import html
import http.cookies
import io
import ipaddress
import json
import logging
import os
import re
import signal
import tempfile
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core, db
from .core import DAYS, Invalid, Forbidden, hm, money

log = logging.getLogger('lessonledger')
esc = lambda v: html.escape('' if v is None else str(v))  # noqa: E731
STATE = {'backup_error': None, 'cfg': None}


class Redirect(Exception):
    def __init__(self, to):
        self.to = to


class Resp:
    def __init__(self, body, status=200, ctype='text/html; charset=utf-8', headers=None):
        self.body = body.encode() if isinstance(body, str) else body
        self.status, self.ctype, self.headers = status, ctype, headers or []


class Req:
    def __init__(self, method, path, query, form, cookies, client):
        self.method, self.path, self.query, self.form, self.cookies, self.client = \
            method, path, query, form, cookies, client
        self.user = self.csrf = self.c = None
        self.sym = '£'

    def q(self, k, default=''):
        return self.query.get(k, [default])[0]

    def f(self, k, default=''):
        return self.form.get(k, [default])[0]

    def fl(self, k):
        return self.form.get(k, [])

    def fdict(self):
        return {k: v[0] for k, v in self.form.items()}

    @property
    def admin(self):
        return self.user and self.user['role'] == 'admin'

    def m(self, cents):
        return money(cents, self.sym)


ROUTES = []


def route(pattern, methods=('GET',), role='user'):
    def deco(fn):
        ROUTES.append((re.compile('^' + pattern + '$'), methods, role, fn))
        return fn
    return deco


# ---------------------------------------------------------------- html helpers

CSS = """
*{box-sizing:border-box}body{font:14px/1.45 system-ui,sans-serif;margin:0;color:#222;background:#f6f7f9}
header{background:#24364b;color:#fff;padding:8px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
header a{color:#fff;text-decoration:none}header .school{font-weight:600;margin-right:12px}header .me{margin-left:auto}
main{padding:16px;max-width:1300px}h1{font-size:22px;margin:4px 0 12px}h2{font-size:17px;margin:18px 0 8px}
table{border-collapse:collapse;background:#fff;margin:6px 0 12px}td,th{border:1px solid #d6dbe1;padding:4px 7px;
text-align:left;vertical-align:top}th{background:#eef1f5}.num{text-align:right;white-space:nowrap}
form.inline{display:inline}.box{background:#fff;border:1px solid #d6dbe1;padding:12px;margin:8px 0;border-radius:4px}
label{display:block;margin:6px 0 2px;font-weight:600}input,select,textarea{font:inherit;padding:4px}
input[type=text],input[type=email],input[type=password],textarea,select{min-width:240px}
.err{color:#b00020;font-weight:400}.errors{background:#fde8ea;border:1px solid #f3b2ba;padding:8px 12px;margin:8px 0}
.msg{background:#e6f4ea;border:1px solid #a8d5b5;padding:8px 12px;margin:8px 0}.banner{background:#fff3cd;
border:1px solid #e8cf73;padding:8px 12px;margin:8px 0}button,.btn{background:#2d6cdf;color:#fff;border:0;
padding:5px 11px;border-radius:3px;cursor:pointer;text-decoration:none;display:inline-block;font:inherit}
button.sec,.btn.sec{background:#6c7a89}button.danger{background:#b3261e}.muted{color:#667}.row{display:flex;
gap:16px;flex-wrap:wrap}.pill{padding:1px 7px;border-radius:9px;background:#e3e8ee;font-size:12px}
.st-paid{background:#cdebd5}.st-void{background:#ddd;text-decoration:line-through}.st-overdue,.st-cancelled
{background:#f8d0d0}.st-draft{background:#fff0c2}.slot{border-left:4px solid #4a90d9;padding:2px 5px;
background:#f7fbff;font-size:12.5px}.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:end}
.filters label{margin:0}.invoice{background:#fff;max-width:800px;padding:24px;border:1px solid #ccc}
@media print{header,.noprint,form,.btn,button{display:none!important}body{background:#fff}main{padding:0}
.invoice{border:0;max-width:none;padding:0}.pagebreak{page-break-after:always}table{page-break-inside:auto}
tr{page-break-inside:avoid}}@page{size:auto;margin:14mm}
"""


def page(req, title, body, bare=False):
    nav = ''
    if req.user and not bare:
        links = [('/', 'Dashboard'), ('/directory/families', 'Directory'), ('/terms', 'Terms'),
                 ('/timetable', 'Timetable'), ('/invoices', 'Invoices'), ('/payments', 'Payments'),
                 ('/reports', 'Reports')]
        if req.admin:
            links.append(('/admin', 'Admin'))
        school = core.setting(req.c, 'school.name')
        nav = (f'<header><span class="school">{esc(school)}</span>' +
               ''.join(f'<a href="{u}">{t}</a>' for u, t in links) +
               f'<span class="me"><a href="/password">{esc(req.user["display_name"])}</a> · '
               f'<form class="inline" method="post" action="/logout">{csrf(req)}'
               f'<button class="sec">Sign out</button></form></span></header>')
    msg = req.q('msg')
    msg = f'<div class="msg">{esc(msg)}</div>' if msg and not bare else ''
    return Resp(f'<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)} – Lesson Ledger</title>'
                f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>'
                f'<body>{nav}<main>{msg}{body}</main></body></html>')


def csrf(req):
    return f'<input type="hidden" name="csrf" value="{esc(req.csrf)}">' if req.csrf else ''


def errbox(errors):
    if not errors:
        return ''
    g = errors.get('_')
    if not g:
        return '<div class="errors">Please correct the marked fields.</div>'
    g = [g] if isinstance(g, str) else g
    return '<div class="errors">' + '<br>'.join(esc(x) for x in g) + '</div>'


def field(name, label, value='', errors=None, typ='text', options=None, extra='', multi=False):
    e = (errors or {}).get(name)
    err = f' <span class="err">{esc(e)}</span>' if e else ''
    if typ == 'textarea':
        inp = f'<textarea name="{name}" rows="3" {extra}>{esc(value)}</textarea>'
    elif typ == 'select':
        vals = {str(v) for v in value} if multi else {str(value)}
        inp = (f'<select name="{name}" {"multiple size=8" if multi else ""} {extra}>' +
               ''.join(f'<option value="{esc(k)}"{" selected" if str(k) in vals else ""}>{esc(v)}</option>'
                       for k, v in options) + '</select>')
    else:
        inp = f'<input type="{typ}" name="{name}" value="{esc(value)}" {extra}>'
    return f'<label>{esc(label)}{err}</label>{inp}'


def btn(req, action, label, cls='', fields=None, confirm=None):
    hidden = ''.join(f'<input type="hidden" name="{k}" value="{esc(v)}">' for k, v in (fields or {}).items())
    conf = f' onsubmit="return confirm(\'{esc(confirm)}\')"' if confirm else ''
    return (f'<form class="inline" method="post" action="{action}"{conf}>{csrf(req)}{hidden}'
            f'<button class="{cls}">{esc(label)}</button></form>')


def table(headers, body_rows, num_cols=()):
    h = ''.join(f'<th class="{"num" if i in num_cols else ""}">{x}</th>' for i, x in enumerate(headers))
    b = ''.join('<tr>' + ''.join(f'<td class="{"num" if i in num_cols else ""}">{x}</td>' for i, x in enumerate(r))
                + '</tr>' for r in body_rows)
    if not body_rows:
        b = f'<tr><td colspan="{len(headers)}" class="muted">Nothing to show.</td></tr>'
    return f'<table><tr>{h}</tr>{b}</table>'


def pill(status):
    return f'<span class="pill st-{esc(status)}">{esc(status)}</span>'


def redirect(to, msg=None):
    if msg:
        to += ('&' if '?' in to else '?') + 'msg=' + urllib.parse.quote(msg)
    raise Redirect(to)


def csv_resp(name, headers, data):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(data)
    return Resp(buf.getvalue(), ctype='text/csv; charset=utf-8',
                headers=[('Content-Disposition', f'attachment; filename="{name}.csv"')])


def opts(c, table_, include_archived_id=None, blank=True):
    rs = core.rows(c, f'SELECT id, name, archived FROM {table_} WHERE archived=0 OR id IS ? ORDER BY name COLLATE NOCASE',
                   include_archived_id)
    return ([('', '— choose —')] if blank else []) + [(r['id'], r['name']) for r in rs]


def term_opts(c):
    return [(t['id'], f"{t['name']} ({t['first_day']} – {t['last_day']})")
            for t in core.rows(c, 'SELECT * FROM terms ORDER BY first_day DESC')]


def pick_term(req):
    tid = req.q('term') or req.f('term')
    if tid.isdigit() and core.row(req.c, 'SELECT 1 FROM terms WHERE id=?', int(tid)):
        return core.term(req.c, int(tid))
    return core.current_term(req.c)


def term_picker(req, t, path, extra=''):
    return (f'<form class="filters noprint" method="get" action="{path}">' +
            field('term', 'Term', t['id'] if t else '', typ='select', options=term_opts(req.c)) + extra +
            '<button class="sec">Show</button></form>')


def write(req, fn, *a, **kw):
    with db.tx(req.c):
        return fn(req.c, req.user, *a, **kw)


# ---------------------------------------------------------------- setup & auth

def is_local(client):
    try:
        ip = ipaddress.ip_address(client)
        return ip.is_loopback or (ip.version == 6 and ip.ipv4_mapped and ip.ipv4_mapped.is_loopback)
    except ValueError:
        return False


@route('/setup', ('GET', 'POST'), role='public')
def setup_page(req):
    if not core.needs_setup(req.c):
        redirect('/login')
    if not is_local(req.client):
        return page(req, 'Setup', '<h1>Setup</h1><div class="errors">Setup must be completed on the server '
                                  'computer.</div>', bare=True)
    errors, f = {}, req.fdict()
    if req.method == 'POST':
        try:
            with db.tx(req.c):
                u = core.setup(req.c, f)
                token = core.create_session(req.c, u)
            return login_cookie(token, '/')
        except Invalid as e:
            errors = e.errors
    tz = f.get('timezone') or core.server_timezone()
    body = (f'<h1>Welcome to Lesson Ledger</h1><p>Set up your school and the owner (admin) account.</p>'
            f'{errbox(errors)}<form method="post" class="box">'
            + field('school_name', 'School name', f.get('school_name', ''), errors)
            + field('address', 'Address', f.get('address', ''), errors, 'textarea')
            + field('currency', 'Currency (3-letter code)', f.get('currency', 'GBP'), errors)
            + field('timezone', 'Time zone', tz, errors)
            + field('display_name', 'Your name', f.get('display_name', ''), errors)
            + field('username', 'Username', f.get('username', ''), errors)
            + field('password', 'Password (at least 10 characters)', '', errors, 'password')
            + field('password2', 'Password again', '', errors, 'password')
            + '<p><button>Create school and sign in</button></p></form>')
    return page(req, 'Setup', body, bare=True)


def login_cookie(token, to):
    return Resp('', 303, headers=[('Location', to), (
        'Set-Cookie', f'll_session={token}; HttpOnly; SameSite=Strict; Path=/')])


@route('/login', ('GET', 'POST'), role='public')
def login_page(req):
    if core.needs_setup(req.c):
        redirect('/setup')
    error = ''
    if req.method == 'POST':
        with db.tx(req.c):  # failed attempts must be committed, so catch inside the transaction
            try:
                u = core.login(req.c, req.f('username'), req.f('password'))
                token = core.create_session(req.c, u)
            except Invalid as e:
                error, u = str(e), None
        if u:
            nxt = req.f('next')
            nxt = nxt if (nxt.startswith('/') and not nxt.startswith('//') and '\\' not in nxt
                          and not any(ord(ch) < 32 for ch in nxt)) else '/'
            return login_cookie(token, '/password' if u['must_change'] else nxt)
    body = (f'<h1>Sign in</h1>{errbox({"_": error} if error else None)}<form method="post" class="box">'
            f'<input type="hidden" name="next" value="{esc(req.q("next") or req.f("next"))}">'
            + field('username', 'Username', req.f('username'), extra='autofocus')
            + field('password', 'Password', '', typ='password') + '<p><button>Sign in</button></p></form>')
    return page(req, 'Sign in', body, bare=True)


@route('/logout', ('POST',))
def logout(req):
    with db.tx(req.c):
        core.end_session(req.c, req.cookies.get('ll_session'))
    return Resp('', 303, headers=[('Location', '/login'), ('Set-Cookie', 'll_session=; Max-Age=0; Path=/')])


@route('/password', ('GET', 'POST'))
def password_page(req):
    errors = {}
    if req.method == 'POST':
        try:
            with db.tx(req.c):
                core.change_password(req.c, req.user, req.f('old'), req.f('password'), req.f('password2'),
                                     req.cookies.get('ll_session'))
            redirect('/', 'Password changed.')
        except Invalid as e:
            errors = e.errors
    note = '<div class="banner">You must set a new password before continuing.</div>' if req.user['must_change'] else ''
    body = (f'<h1>Change password</h1>{note}{errbox(errors)}<form method="post" class="box">{csrf(req)}'
            + field('old', 'Current password', '', errors, 'password')
            + field('password', 'New password', '', errors, 'password')
            + field('password2', 'New password again', '', errors, 'password')
            + '<p><button>Change password</button></p></form>')
    return page(req, 'Change password', body, bare=bool(req.user['must_change']))


# ---------------------------------------------------------------- dashboard

@route('/')
def dashboard(req):
    c = req.c
    counts = {k: core.row(c, f'SELECT COUNT(*) n FROM {k} WHERE archived=0')['n'] for k in core.ENTITIES}
    t = core.current_term(c)
    parts = ['<h1>Dashboard</h1>']
    if req.admin and STATE['backup_error']:
        parts.append(f'<div class="banner">Automatic backup failed: {esc(STATE["backup_error"])}</div>')
    if core.is_empty(c):
        parts.append('<div class="banner">The database is empty. Add records in the Directory, or load demo data '
                     'by stopping the service and running <code>./run.sh demo</code> (empty database only).</div>')
    parts.append('<div class="row">' + ''.join(
        f'<div class="box"><a href="/directory/{k}">{core.ENTITIES[k][1]}</a><br><b>{n}</b></div>'
        for k, n in counts.items()) + '</div>')
    if t:
        invs = core.list_invoices(c, tid=t['id'])
        out = sum(i['balance'] for i in invs if i['status'] not in ('draft', 'void'))
        od = sum(1 for i in invs if i['overdue'])
        nslots = core.row(c, 'SELECT COUNT(*) n FROM slots WHERE term_id=?', t['id'])['n']
        parts.append(f'<div class="box"><h2>{esc(t["name"])}</h2>{esc(t["first_day"])} to {esc(t["last_day"])} · '
                     f'{nslots} weekly slots · {len(invs)} invoices · outstanding {req.m(out)} · '
                     f'{od} overdue<br><a href="/timetable?term={t["id"]}">Timetable</a> · '
                     f'<a href="/lessons?term={t["id"]}">Lessons</a> · <a href="/invoices?term={t["id"]}">Invoices</a>'
                     f'</div>')
    parts.append('<p class="muted">Sections: <a href="/directory/families">Directory</a> · <a href="/terms">Terms</a> · '
                 '<a href="/timetable">Timetable</a> · <a href="/invoices">Invoices</a> · <a href="/payments">'
                 'Payments</a> · <a href="/reports">Reports</a>' + (' · <a href="/admin">Admin</a>' if req.admin else '')
                 + '</p>')
    return page(req, 'Dashboard', ''.join(parts))


# ---------------------------------------------------------------- directory

def dir_tabs(kind):
    return '<p class="noprint">' + ' · '.join(
        (f'<b>{v[1]}</b>' if k == kind else f'<a href="/directory/{k}">{v[1]}</a>')
        for k, v in core.ENTITIES.items()) + '</p>'


@route(r'/directory/(teachers|rooms|lesson_types|families|pupils)')
def dir_list(req, kind):
    label, plural, fields = core.ENTITIES[kind]
    arch = req.q('archived') == '1'
    rs = core.list_records(req.c, kind, req.q('q'), arch)
    cols = [f for f in fields if f[2] not in ('textarea',)]
    fam = {r['id']: r['name'] for r in core.rows(req.c, 'SELECT id,name FROM families')}

    def show(r, f):
        v = r[f[0]]
        if f[2] == 'money':
            return req.m(v)
        if f[2] == 'family':
            return f'<a href="/families/{v}">{esc(fam.get(v))}</a>'
        if f[2] == 'color':
            return f'<span class="pill" style="background:{esc(v)}">&nbsp;&nbsp;</span>'
        return esc(v)
    link = (lambda r: f'/families/{r["id"]}') if kind == 'families' else (lambda r: f'/directory/{kind}/{r["id"]}')
    body = (f'<h1>{plural}</h1>{dir_tabs(kind)}<form class="filters" method="get">'
            f'{field("q", "Search by name", req.q("q"))}'
            f'{field("archived", "Show", "1" if arch else "0", typ="select", options=[("0", "Active"), ("1", "Archived")])}'
            f'<button class="sec">Search</button> <a class="btn" href="/directory/{kind}/new">Add {label.lower()}</a>'
            f'</form>' + table([f[1] for f in cols],
                               [[f'<a href="{link(r)}">{esc(r["name"])}</a>'] + [show(r, f) for f in cols[1:]]
                                for r in rs]))
    return page(req, plural, body)


@route(r'/directory/(teachers|rooms|lesson_types|families|pupils)/(new|\d+)', ('GET', 'POST'))
def dir_edit(req, kind, rid):
    label, plural, fields = core.ENTITIES[kind]
    rid = None if rid == 'new' else int(rid)
    rec = core.get_record(req.c, kind, rid) if rid else None
    if rid and not rec:
        return not_found(req)
    errors, vals = {}, dict(rec or {})
    if kind == 'pupils' and not rid and req.q('family'):
        vals['family_id'] = req.q('family')
    if req.method == 'POST':
        act = req.f('action', 'save')
        try:
            if act == 'save':
                new = write(req, core.save_record, kind, req.fdict(), rid, req.f('version'))
                redirect(f'/families/{new}' if kind == 'families' else f'/directory/{kind}', f'{label} saved.')
            elif act in ('archive', 'restore'):
                write(req, core.set_archived, kind, rid, act == 'archive')
                redirect(f'/directory/{kind}/{rid}', f'{label} {act}d.')
            elif act == 'delete':
                write(req, core.delete_record, kind, rid)
                redirect(f'/directory/{kind}', f'{label} deleted.')
        except Invalid as e:
            errors = e.errors
            vals = dict(e.current) if e.current else (req.fdict() if act == 'save' else vals)
            if e.current is None and act == 'save':
                vals['version'] = req.f('version')
    form = []
    for name, flabel, typ, req_ in fields:
        v = vals.get(name, '')
        if typ == 'money' and isinstance(v, int):
            v = f'{v / 100:.2f}'
        if typ == 'family':
            form.append(field(name, flabel, v, errors, 'select', opts(req.c, 'families', rec and rec['family_id'])))
        else:
            t = {'int': 'number', 'money': 'text', 'date': 'date', 'color': 'color', 'email': 'email'}.get(typ, typ)
            if name == 'max_pupils' and v == '':
                v = 1
            form.append(field(name, flabel, v, errors, t))
    actions = ''
    if rec:
        a = 'restore' if rec['archived'] else 'archive'
        actions = (f'<div class="box">{"<b>Archived.</b> " if rec["archived"] else ""}'
                   f'{btn(req, req.path, a.capitalize(), "sec", {"action": a})} '
                   f'{btn(req, req.path, "Delete permanently", "danger", {"action": "delete"}, "Delete this record?")}'
                   f' <span class="muted">Delete is only possible for records never used in a slot or invoice.</span>'
                   f' · <a href="/admin/audit?entity={kind}&entity_id={rid}">History</a></div>')
    body = (f'<h1>{"Edit" if rec else "Add"} {label.lower()}</h1>{dir_tabs(kind)}{errbox(errors)}'
            f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="save">'
            f'<input type="hidden" name="version" value="{esc(vals.get("version", ""))}">' + ''.join(form) +
            f'<p><button>Save</button> <a href="/directory/{kind}">Cancel</a></p></form>{actions}')
    return page(req, label, body)


@route(r'/families/(\d+)')
def family_page(req, fid):
    c = req.c
    fam = core.get_record(c, 'families', int(fid))
    if not fam:
        return not_found(req)
    pupils = core.rows(c, 'SELECT * FROM pupils WHERE family_id=? ORDER BY name', fam['id'])
    t = core.current_term(c)
    lessons = []
    if t:
        for p in pupils:
            for s in core.slots_full(c, t['id'], pupil_id=p['id']):
                lessons.append([esc(p['name']), esc(s['type_name']), f"{DAYS[s['weekday']]} {hm(s['start_min'])}",
                                esc(s['teacher_name']), esc(s['room_name']), f"{s['start_date']} – {s['end_date']}"])
    invs = core.list_invoices(c, family_id=fam['id'])
    credit = core.family_credit(c, fam['id'])
    body = (f'<h1>{esc(fam["name"])}{" (archived)" if fam["archived"] else ""}</h1>'
            f'<div class="box">{esc(fam["address"]).replace(chr(10), "<br>")}<br>{esc(fam["email"])} · '
            f'{esc(fam["phone"])}<br><span class="muted">{esc(fam["notes"])}</span><br>'
            f'<a href="/directory/families/{fam["id"]}">Edit family</a></div>'
            + (f'<div class="msg">Family credit held: {req.m(credit)} (applied to the next issued invoice)</div>'
               if credit else '') +
            f'<h2>Pupils</h2>' + table(['Name', 'Instrument', 'Date of birth', ''],
                                       [[f'<a href="/directory/pupils/{p["id"]}">{esc(p["name"])}</a>',
                                         esc(p['instrument']), esc(p['dob']), 'archived' if p['archived'] else '']
                                        for p in pupils]) +
            f'<a class="btn sec" href="/directory/pupils/new?family={fam["id"]}">Add pupil</a>' +
            f'<h2>Weekly lessons{" – " + esc(t["name"]) if t else ""}</h2>' +
            table(['Pupil', 'Lesson', 'When', 'Teacher', 'Room', 'Dates'], lessons) +
            '<h2>Invoices</h2>' + invoice_table(req, invs, show_term=True))
    return page(req, fam['name'], body)


def invoice_table(req, invs, show_term=False):
    return table((['Term'] if show_term else []) + ['Family', 'Number', 'Status', 'Lines', 'Total', 'Paid',
                                                    'Balance', 'Due'],
                 [([esc(i['term_name'])] if show_term else []) +
                  [f'<a href="/invoices/{i["id"]}">{esc(i["family_name"])}</a>', esc(i['number'] or '—'),
                   pill('overdue' if i['overdue'] else i['status']) + (' overdue' if i['overdue'] else ''),
                   i['n_lines'], req.m(i['total']), req.m(i['paid']), req.m(i['balance']), esc(i['due_date'] or '')]
                  for i in invs], num_cols=tuple(range(5 + show_term, 8 + show_term)))


# ---------------------------------------------------------------- terms

@route('/terms', ('GET', 'POST'))
def terms_page(req):
    errors, f = {}, req.fdict()
    if req.method == 'POST':
        try:
            tid = write(req, core.save_term, f)
            redirect(f'/terms/{tid}', 'Term created.')
        except Invalid as e:
            errors = e.errors
    ts = core.rows(req.c, 'SELECT * FROM terms ORDER BY first_day DESC')
    body = ('<h1>Terms</h1>' + table(['Name', 'First day', 'Last day', 'Status'],
                                     [[f'<a href="/terms/{t["id"]}">{esc(t["name"])}</a>', t['first_day'],
                                       t['last_day'], 'closed' if t['closed'] else 'open'] for t in ts]) +
            f'<h2>New term</h2>{errbox(errors)}<form method="post" class="box">{csrf(req)}'
            + field('name', 'Name (e.g. Autumn 2026)', f.get('name', ''), errors)
            + field('first_day', 'First day', f.get('first_day', ''), errors, 'date')
            + field('last_day', 'Last day', f.get('last_day', ''), errors, 'date')
            + '<p><button>Create term</button></p></form>')
    return page(req, 'Terms', body)


@route(r'/terms/(\d+)', ('GET', 'POST'))
def term_page(req, tid):
    c, tid = req.c, int(tid)
    t = core.term(c, tid)
    errors, f, report = {}, req.fdict(), ''
    vals = dict(t)
    if req.method == 'POST':
        act = req.f('action')
        try:
            if act == 'save':
                write(req, core.save_term, f, tid, req.f('version'))
                redirect(req.path, 'Term saved.')
            elif act == 'add_skip':
                write(req, core.add_skip, tid, f)
                redirect(req.path, 'Skipped dates added.')
            elif act == 'del_skip':
                write(req, core.delete_skip, int(req.f('skip')))
                redirect(req.path, 'Skipped dates removed.')
            elif act == 'close':
                write(req, core.close_term, tid)
                redirect(req.path, 'Term closed.')
            elif act == 'delete':
                write(req, core.delete_term, tid)
                redirect('/terms', 'Term deleted.')
            elif act == 'copy':
                src = req.f('from')
                if not src.isdigit():
                    raise Invalid({'from': 'Choose a term.'})
                made, skipped = write(req, core.copy_timetable, int(src), tid)
                report = (f'<div class="msg">Copied {made} slot(s).</div>' +
                          (f'<div class="errors"><b>{len(skipped)} slot(s) were not copied:</b><ul>' +
                           ''.join(f'<li>{esc(s)}<ul>' + ''.join(f'<li>{esc(r)}</li>' for r in rs) + '</ul></li>'
                                   for s, rs in skipped) + '</ul></div>' if skipped else ''))
        except Invalid as e:
            errors = e.errors
            if act == 'save':
                vals = dict(e.current) if e.current else dict(t, **f)
    weeks, per_day = core.term_calendar(c, tid)
    sk = core.skips(c, tid)
    others = [(o['id'], o['name']) for o in core.rows(c, 'SELECT * FROM terms WHERE id<>? ORDER BY first_day DESC', tid)]
    body = (f'<h1>{esc(t["name"])}{" (closed)" if t["closed"] else ""}</h1>{errbox(errors)}{report}'
            f'<p><a href="/timetable?term={tid}">Timetable</a> · <a href="/lessons?term={tid}">Dated lessons</a> · '
            f'<a href="/invoices?term={tid}">Invoices</a></p><div class="row"><div>'
            f'<h2>Teaching days per weekday</h2>' + table(DAYS, [per_day], num_cols=tuple(range(7))) +
            '<h2>Teaching weeks</h2>' + table(['Week', 'Week beginning', 'Teaching days'],
                                              [[i + 1, w.isoformat(), n] for i, (w, n) in enumerate(weeks)],
                                              num_cols=(0, 2)) +
            '</div><div><h2>Skipped dates</h2>' +
            table(['From', 'To', 'Label', ''], [[s['start'], s['end'], esc(s['label']),
                                                 btn(req, req.path, 'Remove', 'sec',
                                                     {'action': 'del_skip', 'skip': s['id']})] for s in sk]) +
            f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="add_skip">'
            + field('start', 'From', f.get('start', ''), errors, 'date')
            + field('end', 'To (leave empty for a single day)', f.get('end', ''), errors, 'date')
            + field('label', 'Label', f.get('label', ''), errors)
            + '<p><button>Add skipped dates</button></p></form>'
            f'<h2>Edit term</h2><form method="post" class="box">{csrf(req)}<input type="hidden" name="action" '
            f'value="save"><input type="hidden" name="version" value="{esc(vals.get("version"))}">'
            + field('name', 'Name', vals.get('name'), errors)
            + field('first_day', 'First day', vals.get('first_day'), errors, 'date')
            + field('last_day', 'Last day', vals.get('last_day'), errors, 'date')
            + '<p><button>Save</button></p></form>'
            f'<h2>Copy timetable from another term</h2><form method="post" class="box">{csrf(req)}'
            f'<input type="hidden" name="action" value="copy">'
            + field('from', 'Copy from', '', errors, 'select', [('', '— choose —')] + others)
            + f'<p class="muted">Pupils are {"copied" if core.setting(c, "timetable.copy_pupils") == "copy" else "not copied"} '
              f'(setting timetable.copy_pupils).</p><p><button>Copy slots</button></p></form>'
            f'<div class="box">{btn(req, req.path, "Close term", "sec", {"action": "close"}, "Close this term?")} '
            f'{btn(req, req.path, "Delete term", "danger", {"action": "delete"}, "Delete this term?")}</div>'
            '</div></div>')
    return page(req, t['name'], body)


# ---------------------------------------------------------------- timetable

def grid(req, t, view, slots, print_mode=False):
    c = req.c
    if view == 'teacher':
        cols = [(r['id'], r['name']) for r in core.rows(c, '''SELECT DISTINCT t.id, t.name FROM teachers t JOIN slots s
                ON s.teacher_id=t.id WHERE s.term_id=? ORDER BY t.name''', t['id'])]
        key = 'teacher_id'
    else:
        cols = [(r['id'], r['name']) for r in core.rows(c, '''SELECT id, name FROM rooms WHERE archived=0 OR id IN
                (SELECT room_id FROM slots WHERE term_id=?) ORDER BY name''', t['id'])]
        key = 'room_id'
    used = {s[key] for s in slots}
    cols = [x for x in cols if x[0] in used] if print_mode else cols
    out = []
    for wd in range(7):
        day = [s for s in slots if s['weekday'] == wd]
        if not day:
            continue
        times = sorted({s['start_min'] for s in day})
        rws = []
        for tm in times:
            cells = []
            for cid, _ in cols:
                cell = ''
                for s in day:
                    if s['start_min'] == tm and s[key] == cid:
                        other = s['room_name'] if view == 'teacher' else s['teacher_name']
                        dates = '' if (s['start_date'], s['end_date']) == (t['first_day'], t['last_day']) else \
                            f'<br><span class="muted">{s["start_date"]} – {s["end_date"]}</span>'
                        inner = (f'{hm(s["start_min"])}–{hm(s["end_min"])} <b>{esc(s["type_name"])}</b><br>'
                                 f'{esc(other)}<br>{esc(", ".join(p["name"] for p in s["pupils"]) or "(no pupils)")}'
                                 f'{dates}')
                        if not print_mode:
                            inner = f'<a href="/slots/{s["id"]}">{inner}</a>'
                        cell += f'<div class="slot" style="border-color:{esc(s["colour"])}">{inner}</div>'
                cells.append(cell)
            rws.append([hm(tm)] + cells)
        out.append(f'<h2>{DAYS[wd]}</h2>' + table(['Time'] + [esc(n) for _, n in cols], rws))
    return ''.join(out) or '<p class="muted">No slots.</p>'


@route('/timetable')
def timetable(req):
    t = pick_term(req)
    if not t:
        return page(req, 'Timetable', '<h1>Timetable</h1><p>Create a <a href="/terms">term</a> first.</p>')
    view = req.q('view', 'room')
    filt = {k: req.q(k) for k in ('room_id', 'teacher_id', 'pupil_id')}
    slots = core.slots_full(req.c, t['id'], **filt)
    qs = urllib.parse.urlencode({'term': t['id'], 'view': view, **filt})
    extra = (field('view', 'View', view, typ='select', options=[('room', 'By room'), ('teacher', 'By teacher')]) +
             field('room_id', 'Room', filt['room_id'], typ='select', options=[('', 'All')] + opts(req.c, 'rooms', blank=False)) +
             field('teacher_id', 'Teacher', filt['teacher_id'], typ='select',
                   options=[('', 'All')] + opts(req.c, 'teachers', blank=False)))
    body = (f'<h1>Timetable – {esc(t["name"])}</h1>' + term_picker(req, t, '/timetable', extra) +
            f'<p class="noprint"><a class="btn" href="/slots/new?term={t["id"]}">Add slot</a> '
            f'<a class="btn sec" href="/timetable/print?{qs}">Print view</a> '
            f'<a class="btn sec" href="/lessons?term={t["id"]}">Dated lessons / cancel a lesson</a> '
            f'<span class="muted">{len(slots)} slot(s)</span></p>' + grid(req, t, view, slots))
    return page(req, 'Timetable', body)


@route('/timetable/print')
def timetable_print(req):
    t = pick_term(req)
    view = req.q('view', 'room')
    filt = {k: req.q(k) for k in ('room_id', 'teacher_id')}
    title = 'Whole school'
    if filt['room_id']:
        title = 'Room: ' + core.get_record(req.c, 'rooms', int(filt['room_id']))['name']
    elif filt['teacher_id']:
        title = 'Teacher: ' + core.get_record(req.c, 'teachers', int(filt['teacher_id']))['name']
    slots = core.slots_full(req.c, t['id'], **filt)
    skip = ', '.join(f'{s["label"]} ({s["start"]}–{s["end"]})' for s in core.skips(req.c, t['id']))
    body = (f'<h1>{esc(core.setting(req.c, "school.name"))} – {esc(t["name"])} – {esc(title)}</h1>'
            f'<p>{t["first_day"]} to {t["last_day"]}{". No lessons: " + esc(skip) if skip else ""}</p>'
            f'<p class="noprint"><button onclick="print()">Print</button></p>' + grid(req, t, view, slots, True))
    return page(req, 'Print timetable', body, bare=True)


def slot_form(req, t, vals, errors, sid=None):
    c = req.c
    pupils = core.rows(c, '''SELECT p.id, p.name, f.name fam, p.archived FROM pupils p JOIN families f
                             ON f.id=p.family_id WHERE p.archived=0 OR p.id IN (SELECT pupil_id FROM slot_pupils
                             WHERE slot_id IS ?) ORDER BY p.name''', sid)
    lts = core.rows(c, 'SELECT * FROM lesson_types WHERE archived=0 OR id IS ? ORDER BY name', vals.get('lesson_type_id'))
    return (f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="save">'
            f'<input type="hidden" name="version" value="{esc(vals.get("version", ""))}"><div class="row"><div>'
            + field('weekday', 'Weekday', vals.get('weekday', 0), errors, 'select', list(enumerate(DAYS)))
            + field('start', 'Start time', vals.get('start', ''), errors, 'time', extra='step="300"')
            + field('lesson_type_id', 'Lesson type', vals.get('lesson_type_id', ''), errors, 'select',
                    [('', '— choose —')] + [(r['id'], f"{r['name']} ({r['duration']} min, max {r['max_pupils']}, "
                                                      f"{req.m(r['price'])})") for r in lts])
            + field('teacher_id', 'Teacher', vals.get('teacher_id', ''), errors, 'select',
                    opts(c, 'teachers', vals.get('teacher_id')))
            + field('room_id', 'Room', vals.get('room_id', ''), errors, 'select', opts(c, 'rooms', vals.get('room_id')))
            + '</div><div>'
            + field('pupils', 'Pupils (ctrl/cmd-click for several)', vals.get('pupils', []), errors, 'select',
                    [(p['id'], f"{p['name']} ({p['fam']})") for p in pupils], multi=True)
            + field('start_date', 'Start date', vals.get('start_date', t['first_day']), errors, 'date')
            + field('end_date', 'End date', vals.get('end_date', t['last_day']), errors, 'date')
            + '</div></div><p><button>Save slot</button></p></form>')


@route('/slots/new', ('GET', 'POST'))
def slot_new(req):
    t = pick_term(req)
    if not t:
        redirect('/terms', 'Create a term first.')
    errors, vals = {}, {'start_date': t['first_day'], 'end_date': t['last_day']}
    if req.method == 'POST':
        vals = dict(req.fdict(), pupils=req.fl('pupils'))
        try:
            write(req, core.create_slot, t['id'], vals)
            redirect(f'/timetable?term={t["id"]}', 'Slot added.')
        except Invalid as e:
            errors = e.errors
    body = (f'<h1>Add slot – {esc(t["name"])}</h1>{errbox(errors)}' + slot_form(req, t, vals, errors))
    return page(req, 'Add slot', body)


@route(r'/slots/(\d+)', ('GET', 'POST'))
def slot_edit(req, sid):
    c, sid = req.c, int(sid)
    s = core.get_slot(c, sid)
    t = core.term(c, s['term_id'])
    vals = dict(s, start=hm(s['start_min']))
    errors = {}
    if req.method == 'POST':
        act = req.f('action')
        try:
            if act == 'save':
                vals = dict(req.fdict(), pupils=req.fl('pupils'))
                write(req, core.update_slot, sid, vals, req.f('version'))
                redirect(f'/timetable?term={t["id"]}', 'Slot saved.')
            elif act == 'end':
                write(req, core.end_slot, sid, req.f('from_date'))
                redirect(f'/timetable?term={t["id"]}', 'Slot ended.')
            elif act == 'delete':
                write(req, core.delete_slot, sid)
                redirect(f'/timetable?term={t["id"]}', 'Slot deleted.')
        except Invalid as e:
            errors = e.errors
            if e.current:
                vals = dict(e.current, start=hm(e.current['start_min']))
    inv = core.invoiced_until(c, sid)
    body = (f'<h1>Edit slot – {esc(t["name"])}</h1>{errbox(errors)}'
            + (f'<div class="banner">Lessons up to {inv} are on an issued invoice.</div>' if inv else '')
            + slot_form(req, t, vals, errors, sid) +
            f'<h2>End this slot</h2><form method="post" class="box">{csrf(req)}<input type="hidden" name="action" '
            f'value="end">' + field('from_date', 'No lessons from this date on', req.f('from_date'), errors, 'date') +
            '<p><button class="sec">End slot</button></p></form><div class="box">' +
            btn(req, req.path, 'Delete slot', 'danger', {'action': 'delete'}, 'Delete this slot?') +
            f' · <a href="/lessons?term={t["id"]}&slot={sid}">Dated lessons</a>'
            f' · <a href="/admin/audit?entity=slots&entity_id={sid}">History</a></div>')
    return page(req, 'Edit slot', body)


@route('/lessons', ('GET', 'POST'))
def lessons(req):
    c = req.c
    t = pick_term(req)
    if not t:
        redirect('/terms', 'Create a term first.')
    errors = {}
    if req.method == 'POST':
        try:
            write(req, core.set_occurrence, int(req.f('slot')), req.f('date'), req.f('action'), req.f('reason'),
                  req.f('pupil_id') or None)
            back = req.f('back')
            back = back if back.startswith('/lessons') else f'/lessons?term={t["id"]}'
            redirect(back, 'Lesson updated.')
        except Invalid as e:
            errors = e.errors
    td = core.today(c)
    mon = td - dt.timedelta(days=td.weekday())
    df = req.q('date_from', max(mon, core.d(t['first_day'])).isoformat())
    dto = req.q('date_to', (core.d(df) + dt.timedelta(days=6)).isoformat() if df else '')
    filt = {k: req.q(k) for k in ('room_id', 'teacher_id', 'pupil_id')}
    occ = core.list_occurrences(c, t['id'], date_from=df, date_to=dto, **filt)
    if req.q('slot'):
        occ = [o for o in occ if str(o['slot']['id']) == req.q('slot')]
    absent_note = 'charged' if core.setting(c, 'billing.pupil_absence') == 'charge' else 'not charged'
    back = req.path + '?' + urllib.parse.urlencode({k: v[0] for k, v in req.query.items() if k != 'msg'})
    rws = []
    for o in occ:
        s = o['slot']
        status = ''
        if o['cancelled']:
            status = pill('cancelled') + ' by school: ' + esc(o['cancelled']['reason'])
        for p, st in o['absent']:
            status += f'<br>{esc(p["name"])} absent ({absent_note}) {esc(st["reason"])}'
        form = (f'<form class="inline" method="post">{csrf(req)}<input type="hidden" name="slot" value="{s["id"]}">'
                f'<input type="hidden" name="date" value="{o["date"]}"><input type="hidden" name="back" '
                f'value="{esc(back)}"><select name="action"><option value="cancel">Cancelled by school</option>'
                f'<option value="absent">Pupil absent</option><option value="restore">Restore</option></select> '
                + (f'<select name="pupil_id">' + ''.join(f'<option value="{p["id"]}">{esc(p["name"])}</option>'
                                                        for p in s['pupils']) + '</select> '
                   if len(s['pupils']) > 1 else '') +
                '<input name="reason" placeholder="Reason" size="14"> <button class="sec">Apply</button></form>')
        rws.append([o['date'] + ' ' + DAYS[s['weekday']], f"{hm(s['start_min'])}–{hm(s['end_min'])}",
                    esc(s['type_name']), esc(s['teacher_name']), esc(s['room_name']),
                    esc(', '.join(p['name'] for p in s['pupils'])), status, form])
    pupil_opts = [('', 'All')] + [(p['id'], p['name']) for p in core.rows(c, 'SELECT id,name FROM pupils ORDER BY name')]
    extra = (field('date_from', 'From', df, typ='date') + field('date_to', 'To', dto, typ='date') +
             field('room_id', 'Room', filt['room_id'], typ='select', options=[('', 'All')] + opts(c, 'rooms', blank=False)) +
             field('teacher_id', 'Teacher', filt['teacher_id'], typ='select',
                   options=[('', 'All')] + opts(c, 'teachers', blank=False)) +
             field('pupil_id', 'Pupil', filt['pupil_id'], typ='select', options=pupil_opts))
    body = (f'<h1>Dated lessons – {esc(t["name"])}</h1>{errbox(errors)}' + term_picker(req, t, '/lessons', extra) +
            f'<p class="muted">Pupil absences are {absent_note} (setting billing.pupil_absence). {len(occ)} lesson(s).</p>' +
            table(['Date', 'Time', 'Lesson', 'Teacher', 'Room', 'Pupils', 'Status', 'Action'], rws))
    return page(req, 'Lessons', body)


# ---------------------------------------------------------------- invoices

@route('/invoices', ('GET', 'POST'))
def invoices(req):
    c = req.c
    t = pick_term(req)
    if not t:
        redirect('/terms', 'Create a term first.')
    errors = {}
    if req.method == 'POST':
        act = req.f('action')
        try:
            if act == 'generate':
                n = write(req, core.generate_drafts, t['id'])
                redirect(f'/invoices?term={t["id"]}', f'{n} new draft(s) created.')
            elif act == 'regenerate':
                n = write(req, core.regenerate, t['id'])
                redirect(f'/invoices?term={t["id"]}', f'{n} draft(s) rebuilt from the timetable.')
            elif act == 'issue_all':
                n, refused = write(req, core.issue_all, t['id'])
                if refused:
                    errors = {'_': [f'{n} invoice(s) issued. Not issued:'] + refused}
                else:
                    redirect(f'/invoices?term={t["id"]}', f'{n} invoice(s) issued.')
        except Invalid as e:
            errors = e.errors
    invs = core.list_invoices(c, tid=t['id'])
    st = req.q('status')
    if st:
        invs = [i for i in invs if i['status'] == st or (st == 'overdue' and i['overdue'])]
    extra = field('status', 'Status', st, typ='select', options=[('', 'All'), ('draft', 'Draft'), ('issued', 'Issued'),
                                                                 ('part-paid', 'Part-paid'), ('paid', 'Paid'),
                                                                 ('overdue', 'Overdue'), ('void', 'Void')])
    tot = sum(i['total'] for i in invs if i['status'] != 'void')
    body = (f'<h1>Invoices – {esc(t["name"])}</h1>{errbox(errors)}' + term_picker(req, t, '/invoices', extra) +
            '<div class="box noprint">' +
            btn(req, f'/invoices?term={t["id"]}', 'Generate drafts', '', {'action': 'generate'}) + ' ' +
            btn(req, f'/invoices?term={t["id"]}', 'Regenerate drafts', 'sec', {'action': 'regenerate'}) + ' ' +
            btn(req, f'/invoices?term={t["id"]}', 'Issue all drafts', 'sec', {'action': 'issue_all'},
                'Issue every draft for this term?') +
            f' <a class="btn sec" href="/invoices/print?term={t["id"]}">Print all issued</a></div>' +
            invoice_table(req, invs) + f'<p>{len(invs)} invoice(s), total {req.m(tot)} (excluding void).</p>')
    return page(req, 'Invoices', body)


def invoice_doc(req, inv):
    c = req.c
    fig = core.invoice_figures(c, inv)
    lines = core.invoice_lines(c, inv['id'])
    sk = core.skips(c, inv['term_id'])
    cns = core.rows(c, 'SELECT * FROM credit_notes WHERE invoice_id=? ORDER BY id', inv['id'])
    s = core.all_settings(c)
    rws = []
    for ln in lines:
        dates = ''
        if ln['dates']:
            dates = '<br><span class="muted">Lessons: ' + ', '.join(
                core.d(x).strftime('%d %b') for x in ln['dates'].split(',')) + '</span>'
        rws.append([esc(ln['description']) + dates, req.m(ln['amount'])])
    title = {'draft': 'DRAFT INVOICE', 'void': 'VOID INVOICE'}.get(inv['status'], 'INVOICE')
    return (f'<div class="invoice"><div class="row" style="justify-content:space-between"><div>'
            f'<b style="font-size:18px">{esc(s["school.name"])}</b><br>{esc(s["school.address"]).replace(chr(10), "<br>")}'
            f'</div><div style="text-align:right"><b style="font-size:18px">{title}</b><br>'
            f'Number: {esc(inv["number"] or "—")}<br>Issued: {esc(inv["issue_date"] or "—")}<br>'
            f'Due: {esc(inv["due_date"] or "—")}<br>Term: {esc(inv["term_name"])}</div></div>'
            f'<p><b>Bill to:</b><br>{esc(inv["family_name"])}<br>{esc(inv["family_address"]).replace(chr(10), "<br>")}</p>'
            + table(['Description', 'Amount'], rws, num_cols=(1,)) +
            (table(['Credit note', 'Reason', 'Amount'],
                   [[f'CN-{cn["id"]} ({cn["created_at"][:10]})',
                     esc(cn['reason']) + ''.join(f'<br>{esc(x["description"])}' for x in json.loads(cn['lines'])),
                     req.m(-cn['amount'])] for cn in cns], num_cols=(2,)) if cns else '') +
            table(['', ''], [['Total', req.m(fig['total'])], ['Credits', req.m(-fig['credited'])],
                             ['Paid', req.m(-fig['paid'])], ['Refunded', req.m(fig['refunded'])],
                             ['<b>Balance due</b>', f'<b>{req.m(fig["balance"])}</b>']], num_cols=(1,)) +
            (f'<p><b>No lessons on:</b> ' + '; '.join(f'{esc(x["label"])} ({x["start"]}' +
                                                      (f' – {x["end"]}' if x['end'] != x['start'] else '') + ')'
                                                      for x in sk) + '</p>' if sk else '') +
            (f'<p><b>VOID:</b> {esc(inv["void_reason"])}</p>' if inv['status'] == 'void' else '') + '</div>')


@route(r'/invoices/(\d+)', ('GET', 'POST'))
def invoice_page(req, iid):
    c, iid = req.c, int(iid)
    inv = core.get_invoice(c, iid)
    errors = {}
    if req.method == 'POST':
        act = req.f('action')
        f = req.fdict()
        msgs = {'adjust': 'Adjustment added.', 'remove_adj': 'Adjustment removed.', 'regenerate': 'Draft rebuilt.',
                'issue': 'Invoice issued.', 'pay': 'Payment recorded.', 'mark_paid': 'Marked paid.',
                'reverse': 'Payment reversed.', 'refund': 'Refund recorded.', 'credit': 'Credit note created.',
                'void': 'Invoice voided.'}
        try:
            if act == 'adjust':
                write(req, core.add_adjustment, iid, f)
            elif act == 'remove_adj':
                write(req, core.remove_adjustment, int(f['line']))
            elif act == 'regenerate':
                write(req, core.regenerate, inv['term_id'], iid)
            elif act == 'issue':
                write(req, core.issue, iid)
            elif act == 'pay':
                write(req, core.record_payment, iid, f)
            elif act == 'mark_paid':
                write(req, core.mark_paid, iid, f.get('method'))
            elif act == 'reverse':
                write(req, core.reverse_payment, int(f['entry']), f.get('reason'))
            elif act == 'refund':
                write(req, core.refund, iid, f)
            elif act == 'credit':
                write(req, core.credit_note, iid, f)
            elif act == 'void':
                write(req, core.void_invoice, iid, f.get('reason'))
            redirect(req.path, msgs.get(act, 'Done.'))
        except Invalid as e:
            errors = e.errors
    inv = core.get_invoice(c, iid)
    fig = core.invoice_figures(c, inv)
    f = req.fdict() if errors else {}
    methods = [(m, m) for m in core.METHODS]
    parts = [f'<h1>Invoice {esc(inv["number"] or "(draft)")} – {esc(inv["family_name"])} {pill(fig["status"])}'
             f'{" " + pill("overdue") if fig["overdue"] else ""}</h1>{errbox(errors)}'
             f'<p class="noprint"><a href="/invoices?term={inv["term_id"]}">All invoices for {esc(inv["term_name"])}</a>'
             f' · <a href="/families/{inv["family_id"]}">Family page</a> · <a href="/invoices/{iid}/print">Printable page</a>'
             f' · <a href="/admin/audit?entity=invoices&entity_id={iid}">History</a></p>', invoice_doc(req, inv)]
    if inv['status'] == 'draft':
        adj = [ln for ln in core.invoice_lines(c, iid) if ln['kind'] == 'adjustment']
        parts.append(
            '<div class="noprint"><h2>Adjustments</h2>' +
            table(['Description', 'Amount', ''], [[esc(a['description']), req.m(a['amount']),
                                                   btn(req, req.path, 'Remove', 'sec', {'action': 'remove_adj', 'line': a['id']})]
                                                  for a in adj], num_cols=(1,)) +
            f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="adjust">' +
            field('description', 'Description', f.get('description', ''), errors) +
            field('amount', 'Amount (negative for a discount, e.g. -10.00)', f.get('amount', ''), errors) +
            '<p><button>Add adjustment</button></p></form><div class="box">' +
            btn(req, req.path, 'Regenerate from timetable', 'sec', {'action': 'regenerate'}) + ' ' +
            btn(req, req.path, 'Issue invoice', '', {'action': 'issue'}, 'Issue this invoice? It will be frozen.') +
            '</div></div>')
    if inv['status'] == 'issued':
        ents = core.invoice_entries(c, iid)
        parts.append(
            '<div class="noprint"><h2>Payments and corrections</h2>' +
            table(['Date', 'Kind', 'Method', 'Reference / reason', 'Amount', 'By', ''],
                  [[e['date'], e['kind'], esc(e['method']), esc(e['reference']) + ' ' + esc(e['reason']),
                    req.m(e['amount']), esc(e['username']),
                    (f'<form class="inline" method="post">{csrf(req)}<input type="hidden" name="action" value="reverse">'
                     f'<input type="hidden" name="entry" value="{e["id"]}"><input name="reason" placeholder="Reason" '
                     f'size="12"> <button class="sec">Reverse</button></form>'
                     if e['kind'] == 'payment' and not e['reversed'] else ('reversed' if e['reversed'] else ''))]
                   for e in ents], num_cols=(4,)) + '<div class="row">')
        if fig['balance'] > 0:
            parts.append(
                f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="pay">'
                f'<b>Record payment</b>' +
                field('amount', 'Amount', f.get('amount', f'{fig["balance"] / 100:.2f}'), errors) +
                field('date', 'Date', f.get('date', core.today(c).isoformat()), errors, 'date') +
                field('method', 'Method', f.get('method', ''), errors, 'select', [('', '— choose —')] + methods) +
                field('reference', 'Reference (optional)', f.get('reference', ''), errors) +
                '<p><button>Record payment</button></p></form>'
                f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="mark_paid">'
                f'<b>Mark paid ({req.m(fig["balance"])})</b>' +
                field('method', 'Method', '', None, 'select', [('', '— choose —')] + methods, extra='required') +
                '<p><button>Mark paid</button></p></form>')
        if fig['overpaid'] > 0:
            parts.append(
                f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="refund">'
                f'<b>Refund (overpaid {req.m(fig["overpaid"])})</b>' +
                field('amount', 'Amount', f.get('amount', f'{fig["overpaid"] / 100:.2f}'), errors) +
                field('date', 'Date', f.get('date', core.today(c).isoformat()), errors, 'date') +
                field('method', 'Method', f.get('method', ''), errors, 'select', [('', '— choose —')] + methods) +
                field('reason', 'Note', f.get('reason', ''), errors) + '<p><button>Record refund</button></p></form>')
        parts.append(
            f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="credit">'
            f'<b>Credit note</b>' + field('reason', 'Reason', f.get('reason', ''), errors) +
            field('lines', 'Lines, one per row: description | amount', f.get('lines', ''), errors, 'textarea',
                  extra='placeholder="Lesson cancelled 14 Oct | 21.00"') +
            '<p><button class="sec">Create credit note</button></p></form>')
    if inv['status'] in ('issued', 'draft'):
        parts.append(
            f'<form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="void">'
            f'<b>Void invoice</b><p class="muted">Voiding keeps the invoice and its number. Afterwards, '
            f'"Generate drafts" on the term creates a new draft for this family.</p>' +
            field('reason', 'Reason', '', errors) + '<p><button class="danger">Void</button></p></form>')
    parts.append('</div></div>' if inv['status'] == 'issued' else '')
    return page(req, 'Invoice', ''.join(parts))


@route(r'/invoices/(\d+)/print')
def invoice_print(req, iid):
    inv = core.get_invoice(req.c, int(iid))
    return page(req, f'Invoice {inv["number"] or ""}', '<p class="noprint"><button onclick="print()">Print</button>'
                                                       '</p>' + invoice_doc(req, inv), bare=True)


@route('/invoices/print')
def invoice_print_all(req):
    t = pick_term(req)
    invs = [i for i in core.list_invoices(req.c, tid=t['id']) if i['status'] not in ('draft', 'void')]
    docs = '<div class="pagebreak"></div>'.join(invoice_doc(req, core.get_invoice(req.c, i['id'])) for i in invs)
    return page(req, 'Invoices', f'<p class="noprint">{len(invs)} issued invoice(s). <button onclick="print()">Print'
                                 f'</button></p>' + (docs or '<p>No issued invoices.</p>'), bare=True)


# ---------------------------------------------------------------- reports

def report_links(req, t):
    return (f'<p class="noprint"><a href="/reports?term={t["id"] if t else ""}">Term billing</a> · '
            f'<a href="/payments">Payments</a> · <a href="/reports/teachers?term={t["id"] if t else ""}">Teacher lessons</a>'
            f' · <button onclick="print()">Print</button></p>')


@route('/reports')
def term_report_page(req):
    t = pick_term(req)
    if not t:
        return page(req, 'Reports', '<h1>Reports</h1><p>No terms yet.</p>' + report_links(req, t))
    data, totals, overdue = core.term_report(req.c, t['id'])
    keys = ['invoiced', 'credited', 'paid', 'refunded', 'outstanding']
    if req.q('csv'):
        return csv_resp(f'term-billing-{t["name"]}', ['Family', 'Invoices'] + [k.capitalize() for k in keys],
                        [[r['family'], ' '.join(r['invoices'])] + [f'{r[k] / 100:.2f}' for k in keys] for r in data] +
                        [['TOTAL', ''] + [f'{totals[k] / 100:.2f}' for k in keys]])
    body = (f'<h1>Term billing report – {esc(t["name"])}</h1>' + report_links(req, t) +
            term_picker(req, t, '/reports') + f'<p><a class="btn sec noprint" href="?term={t["id"]}&csv=1">Download CSV</a>'
            f' Overdue invoices: <b>{overdue}</b></p>' +
            table(['Family', 'Invoice'] + [k.capitalize() for k in keys],
                  [[esc(r['family']), esc(' '.join(r['invoices']))] + [req.m(r[k]) for k in keys] for r in data] +
                  [['<b>Total</b>', ''] + [f'<b>{req.m(totals[k])}</b>' for k in keys]], num_cols=tuple(range(2, 7))))
    return page(req, 'Term billing report', body)


@route('/payments')
def payments_page(req):
    errors = {}
    try:
        start, end = core.parse_range(req.c, {'start': req.q('start'), 'end': req.q('end')})
    except Invalid as e:
        errors = e.errors
        start, end = core.parse_range(req.c, {})
    es, by_method, by_day, total = core.payments_report(req.c, start, end)
    if req.q('csv') and not errors:
        return csv_resp(f'payments-{start}-{end}', ['Date', 'Kind', 'Family', 'Invoice', 'Method', 'Reference',
                                                    'Reason', 'Amount'],
                        [[e['date'], e['kind'], e['family_name'], e['number'] or '', e['method'], e['reference'],
                          e['reason'], f'{e["amount"] / 100:.2f}'] for e in es] +
                        [['TOTAL', '', '', '', '', '', '', f'{total / 100:.2f}']] +
                        [['Method total', '', '', '', m, '', '', f'{v / 100:.2f}'] for m, v in sorted(by_method.items())])
    qs = urllib.parse.urlencode({'start': start, 'end': end, 'csv': 1})
    body = (f'<h1>Payments report</h1>{errbox(errors)}' + report_links(req, core.current_term(req.c)) +
            '<form class="filters noprint" method="get">' +
            field('start', 'From', req.q('start') or start.isoformat(), errors, 'date') +
            field('end', 'To', req.q('end') or end.isoformat(), errors, 'date') +
            f'<button class="sec">Show</button> <a class="btn sec" href="/payments?{qs}">Download CSV</a></form>'
            f'<p>{start} to {end}</p><div class="row"><div><h2>By method</h2>' +
            table(['Method', 'Total'], [[esc(m), req.m(v)] for m, v in sorted(by_method.items())] +
                  [['<b>Total</b>', f'<b>{req.m(total)}</b>']], num_cols=(1,)) + '</div><div><h2>By day</h2>' +
            table(['Day', 'Total'], [[k, req.m(v)] for k, v in sorted(by_day.items())], num_cols=(1,)) +
            '</div></div><h2>Entries</h2>' +
            table(['Date', 'Kind', 'Family', 'Invoice', 'Method', 'Reference / reason', 'Amount'],
                  [[e['date'], e['kind'], esc(e['family_name']),
                    f'<a href="/invoices/{e["invoice_id"]}">{esc(e["number"])}</a>' if e['invoice_id'] else '',
                    esc(e['method']), esc(e['reference'] + ' ' + e['reason']), req.m(e['amount'])] for e in es],
                  num_cols=(6,)))
    return page(req, 'Payments', body)


@route('/reports/teachers')
def teacher_report_page(req):
    t = pick_term(req)
    if not t:
        redirect('/reports')
    data = core.teacher_report(req.c, t['id'])
    if req.q('csv'):
        return csv_resp(f'teacher-lessons-{t["name"]}', ['Teacher', 'Delivered', 'Cancelled', 'Still scheduled'],
                        [[r['teacher'], r['delivered'], r['cancelled'], r['scheduled']] for r in data])
    body = (f'<h1>Teacher lesson report – {esc(t["name"])}</h1>' + report_links(req, t) +
            term_picker(req, t, '/reports/teachers') +
            f'<p><a class="btn sec noprint" href="?term={t["id"]}&csv=1">Download CSV</a> '
            f'<span class="muted">Delivered = lesson dates up to today not cancelled by the school.</span></p>' +
            table(['Teacher', 'Delivered', 'Cancelled', 'Still scheduled'],
                  [[esc(r['teacher']), r['delivered'], r['cancelled'], r['scheduled']] for r in data],
                  num_cols=(1, 2, 3)))
    return page(req, 'Teacher lessons', body)


# ---------------------------------------------------------------- admin

@route('/admin', role='admin')
def admin_home(req):
    banner = (f'<div class="banner">Automatic backup failed: {esc(STATE["backup_error"])}</div>'
              if STATE['backup_error'] else '')
    cfg = STATE['cfg'] or {}
    body = (f'<h1>Admin</h1>{banner}<div class="row">'
            '<div class="box"><a href="/admin/users">Users</a><br>Add staff, reset passwords, deactivate.</div>'
            '<div class="box"><a href="/admin/settings">Settings</a><br>School details and switches.</div>'
            '<div class="box"><a href="/admin/backup">Backup</a><br>Download a backup now.</div>'
            '<div class="box"><a href="/admin/audit">Audit log</a><br>Every change, who and when.</div></div>'
            f'<p class="muted">Data directory: {esc(cfg.get("data_dir"))}<br>Backup folder: {esc(cfg.get("backup_dir"))}</p>')
    return page(req, 'Admin', body)


@route('/admin/users', ('GET', 'POST'), role='admin')
def admin_users(req):
    errors, f = {}, req.fdict()
    if req.method == 'POST':
        act = req.f('action')
        try:
            if act == 'add':
                write(req, core.create_user, dict(f, password2=f.get('password')))
                redirect(req.path, 'User added. They must change the password at first sign-in.')
            uid = int(f['user'])
            if act == 'update':
                write(req, core.update_user, uid, {'display_name': f.get('display_name'), 'role': f.get('role')})
            elif act in ('deactivate', 'reactivate'):
                write(req, core.update_user, uid, {'active': 1 if act == 'reactivate' else 0})
            elif act == 'reset':
                write(req, core.reset_password, uid, f.get('password'))
            redirect(req.path, 'User updated.')
        except Invalid as e:
            errors = e.errors
            if '_' not in errors:
                errors['_'] = '; '.join(v for v in errors.values() if isinstance(v, str))
    us = core.rows(req.c, 'SELECT * FROM users ORDER BY username')
    rws = []
    for u in us:
        rws.append([
            esc(u['username']),
            f'<form class="inline" method="post">{csrf(req)}<input type="hidden" name="action" value="update">'
            f'<input type="hidden" name="user" value="{u["id"]}"><input name="display_name" value="{esc(u["display_name"])}">'
            f' <select name="role">' + ''.join(f'<option{" selected" if u["role"] == r else ""}>{r}</option>'
                                               for r in ('staff', 'admin')) +
            '</select> <button class="sec">Save</button></form>',
            ('active' if u['active'] else 'deactivated') + (' · must change password' if u['must_change'] else '') +
            (' · locked' if u['locked_until'] > time.time() else ''),
            btn(req, req.path, 'Deactivate' if u['active'] else 'Reactivate', 'sec',
                {'action': 'deactivate' if u['active'] else 'reactivate', 'user': u['id']}) +
            f' <form class="inline" method="post">{csrf(req)}<input type="hidden" name="action" value="reset">'
            f'<input type="hidden" name="user" value="{u["id"]}"><input type="password" name="password" '
            f'placeholder="Temporary password" size="14"> <button class="sec">Reset password</button></form>'])
    body = (f'<h1>Users</h1>{errbox(errors)}' + table(['Username', 'Name and role', 'Status', 'Actions'], rws) +
            f'<h2>Add user</h2><form method="post" class="box">{csrf(req)}<input type="hidden" name="action" value="add">'
            + field('username', 'Username', f.get('username', '') if f.get('action') == 'add' else '', errors)
            + field('display_name', 'Display name', f.get('display_name', '') if f.get('action') == 'add' else '', errors)
            + field('role', 'Role', f.get('role', 'staff'), errors, 'select', [('staff', 'Staff'), ('admin', 'Admin')])
            + field('password', 'Temporary password', '', errors, 'password')
            + '<p><button>Add user</button></p></form>')
    return page(req, 'Users', body)


SETTING_LABELS = [
    ('school.name', 'School name'), ('school.address', 'School address'), ('school.currency', 'Currency'),
    ('school.timezone', 'Time zone'), ('hours.open', 'Opening time'), ('hours.close', 'Closing time'),
    ('invoices.due_days', 'Days until an invoice is due'),
    ('billing.pupil_absence', 'Lessons marked "pupil absent" are'),
    ('payments.overpayment', 'A payment above the balance is'), ('invoices.void_permission', 'Who may void invoices'),
    ('timetable.copy_pupils', 'Copying a timetable'),
    ('timetable.end_within_hours', 'Opening hours apply to'),
    ('invoices.number_year', 'Year in invoice numbers comes from'),
    ('directory.archive_family_with_active_pupils', 'Archiving a family whose pupils have current lessons is'),
    ('payments.before_issue_date', 'Payments dated before the invoice issue date are'), ('auth.min_password', 'Minimum password length'),
    ('auth.session_hours', 'Sessions expire after (hours idle)'),
    ('auth.lockout_attempts', 'Failed sign-ins before lockout'), ('auth.lockout_minutes', 'Lockout minutes'),
]


@route('/admin/settings', ('GET', 'POST'), role='admin')
def admin_settings(req):
    errors = {}
    vals = core.all_settings(req.c)
    if req.method == 'POST':
        try:
            write(req, core.set_settings, req.fdict())
            redirect(req.path, 'Settings saved.')
        except Invalid as e:
            errors = e.errors
            vals.update(req.fdict())
    form = ''.join(
        field(k, f'{label} ({k})', vals[k], errors, 'select', [(x, x) for x in core.CHOICES[k]]) if k in core.CHOICES
        else field(k, label, vals[k], errors, 'textarea' if k == 'school.address' else 'text')
        for k, label in SETTING_LABELS)
    return page(req, 'Settings', f'<h1>Settings</h1>{errbox(errors)}<form method="post" class="box">{csrf(req)}'
                                 f'{form}<p><button>Save settings</button></p></form>')


@route('/admin/backup', role='admin')
def admin_backup(req):
    cfg = STATE['cfg'] or {}
    files = []
    if cfg.get('backup_dir') and os.path.isdir(cfg['backup_dir']):
        files = sorted(os.listdir(cfg['backup_dir']), reverse=True)[:30]
    banner = (f'<div class="banner">Automatic backup failed: {esc(STATE["backup_error"])}</div>'
              if STATE['backup_error'] else '')
    body = (f'<h1>Backup</h1>{banner}<p><a class="btn" href="/admin/backup/download">Download backup</a></p>'
            f'<p>The file contains all data, settings and the schema version. To restore, stop the service and run '
            f'<code>./run.sh restore FILE</code> (see README).</p><h2>Automatic backups in {esc(cfg.get("backup_dir"))}'
            f'</h2><ul>' + ''.join(f'<li>{esc(x)}</li>' for x in files) + '</ul>')
    return page(req, 'Backup', body)


@route('/admin/backup/download', role='admin')
def admin_backup_download(req):
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    try:
        db.backup_to(req.c, path)
        with open(path, 'rb') as fh:
            data = fh.read()
    finally:
        os.remove(path)
    with db.tx(req.c):
        core.audit(req.c, req.user, 'download_backup', 'backup', None)
    name = f'lessonledger-backup-{dt.datetime.now().strftime("%Y%m%d-%H%M%S")}.db'
    return Resp(data, ctype='application/octet-stream',
                headers=[('Content-Disposition', f'attachment; filename="{name}"')])


@route('/admin/audit', role='admin')
def admin_audit(req):
    ents = ['', 'users', 'settings', 'teachers', 'rooms', 'lesson_types', 'families', 'pupils', 'terms', 'slots',
            'invoices', 'backup']
    rs = core.audit_log(req.c, req.q('entity'), req.q('entity_id'), req.q('start'), req.q('end'))

    def short(v):
        return esc(v if v is None or len(v) < 400 else v[:400] + '…')
    body = ('<h1>Audit log</h1><form class="filters" method="get">' +
            field('entity', 'Record type', req.q('entity'), typ='select', options=[(e, e or 'All') for e in ents]) +
            field('entity_id', 'Record id', req.q('entity_id')) + field('start', 'From', req.q('start'), typ='date') +
            field('end', 'To', req.q('end'), typ='date') + '<button class="sec">Filter</button></form>' +
            table(['When (UTC)', 'User', 'Action', 'Record', 'Before', 'After'],
                  [[r['at'], esc(r['username']), esc(r['action']), f'{esc(r["entity"])} {r["entity_id"] or ""}',
                    f'<code>{short(r["before"])}</code>', f'<code>{short(r["after"])}</code>'] for r in rs]) +
            '<p class="muted">Showing up to 500 most recent entries.</p>')
    return page(req, 'Audit log', body)


def not_found(req):
    r = page(req, 'Not found', '<h1>Not found</h1><p><a href="/">Back to the dashboard</a></p>')
    r.status = 404
    return r


# ---------------------------------------------------------------- server plumbing

class Handler(BaseHTTPRequestHandler):
    server_version = 'LessonLedger'

    def log_message(self, fmt, *args):
        log.debug('%s %s', self.client_address[0], fmt % args)

    def do_GET(self):
        self.handle_any('GET')

    def do_POST(self):
        self.handle_any('POST')

    def handle_any(self, method):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        form = {}
        if method == 'POST':
            try:
                n = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                n = -1
            if n < 0:
                self.close_connection = True
                return self.send(Resp('Bad Content-Length', 400, 'text/plain'))
            if n > 2_000_000:
                return self.send(Resp('Request too large', 413, 'text/plain'))
            form = urllib.parse.parse_qs(self.rfile.read(n).decode('utf-8', 'replace'), keep_blank_values=True)
        cookies = {}
        if self.headers.get('Cookie'):
            ck = http.cookies.SimpleCookie()
            try:
                ck.load(self.headers['Cookie'])
                cookies = {k: v.value for k, v in ck.items()}
            except http.cookies.CookieError:
                pass
        req = Req(method, url.path, query, form, cookies, self.client_address[0])
        req.c = db.connect(self.server.cfg['db_path'])
        try:
            self.send(dispatch(req))
        except Exception:
            stamp = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log.error('Server error at %s on %s %s\n%s', stamp, method, self.path, traceback.format_exc())
            self.send(Resp(f'<!doctype html><h1>Something went wrong</h1><p>The error was logged at {stamp}. '
                           f'Please try again or tell the administrator the time.</p><p><a href="/">Dashboard</a></p>',
                           500))
        finally:
            req.c.close()

    def send(self, r):
        self.send_response(r.status)
        self.send_header('Content-Type', r.ctype)
        self.send_header('Content-Length', str(len(r.body)))
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        for k, v in r.headers:
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(r.body)


def dispatch(req):
    c = req.c
    try:
        for rx, methods, role, fn in ROUTES:
            m = rx.match(req.path)
            if not m:
                continue
            if req.method not in methods:
                return Resp('Method not allowed', 405, 'text/plain')
            if role != 'public':
                if core.needs_setup(c):
                    redirect('/setup')
                s = core.get_session(c, req.cookies.get('ll_session'))
                if not s:
                    redirect('/login?next=' + urllib.parse.quote(req.path) if req.method == 'GET' else '/login')
                req.user, req.csrf = s
                if req.method == 'POST' and req.f('csrf') != req.csrf:
                    return Resp('This form has expired. Go back, reload the page and try again.', 403, 'text/plain')
                if req.user['must_change'] and req.path not in ('/password', '/logout'):
                    redirect('/password')
                if role == 'admin' and req.user['role'] != 'admin':
                    raise Forbidden('Only an admin can do that.')
            req.sym = core.currency_symbol(c)
            return fn(req, *m.groups())
        return not_found(req)
    except Redirect as r:
        return Resp('', 303, headers=[('Location', r.to)])
    except Forbidden as e:
        resp = page(req, 'Not allowed', f'<h1>Not allowed</h1><div class="errors">{esc(e)}</div>')
        resp.status = 403
        return resp
    except Invalid as e:
        resp = page(req, 'Error', f'<h1>Cannot do that</h1>{errbox(e.errors if "_" in e.errors else {"_": str(e)})}'
                                  f'<p><a href="javascript:history.back()">Go back</a></p>')
        resp.status = 400
        return resp


def backup_loop(cfg, stop):
    while True:
        try:
            c = db.connect(cfg['db_path'])
            try:
                path = db.write_backup(c, cfg)
            finally:
                c.close()
            STATE['backup_error'] = None
            log.info('Automatic backup written: %s', path)
        except Exception as e:
            STATE['backup_error'] = f'{e} ({dt.datetime.now():%Y-%m-%d %H:%M})'
            log.error('Automatic backup failed: %s', e)
        if stop.wait(24 * 3600):
            return


def make_server(cfg):
    srv = ThreadingHTTPServer((cfg['host'], cfg['port']), Handler)
    srv.daemon_threads = True
    srv.cfg = cfg
    STATE['cfg'] = cfg
    return srv


def serve(cfg):
    c = db.open_db(cfg)
    c.close()
    try:
        srv = make_server(cfg)
    except OSError as e:
        raise SystemExit(f'Cannot listen on {cfg["host"]}:{cfg["port"]} ({e.strerror}). Port {cfg["port"]} may '
                         f'already be in use: set LL_PORT (or "port" in lessonledger.conf) to another port.')
    pidfile = os.path.join(cfg['data_dir'], 'lessonledger.pid')
    with open(pidfile, 'w') as fh:
        fh.write(str(os.getpid()))
    stop = threading.Event()

    def on_term(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, on_term)
    threading.Thread(target=backup_loop, args=(cfg, stop), daemon=True).start()
    host = 'localhost' if cfg['host'] in ('127.0.0.1', '::1') else cfg['host']
    print(f'Lesson Ledger is running. Open http://{host}:{cfg["port"]}/ in a browser. Press Ctrl+C to stop.',
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        srv.server_close()
        try:
            os.remove(pidfile)
        except OSError:
            pass
