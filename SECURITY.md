# Security

How Lesson Ledger was reviewed for security before its first release, what was found, and what is still open.

## Threat model

A single-school office web app (Python standard library + SQLite). It listens on 127.0.0.1:8080 by default; the operator can open it to the LAN. Every page except /login and the one-time /setup needs a signed-in staff or admin session; admin-only areas are user management, settings, backups and the audit log. Anyone who can reach the port can talk to the HTTP parser and the login form.

### Entry points

| entry point | who can reach it | authentication | notes |
|---|---|---|---|
| GET/POST /setup | local | none; only before the first user exists, and only from a loopback address | no CSRF token or Origin check on the POST |
| GET/POST /login | public | username + password; 5 failures lock the account for 15 minutes | takes a next= redirect target |
| Any request to the HTTP server (header and body parsing) | public | none | the body is read before any route or session check (web.py:1252) |
| POST /logout, GET/POST /password | staff | session cookie + CSRF token |  |
| Directory, terms, timetable, slots, lessons, invoices, payments, reports (GET/POST) | staff | session cookie; every POST needs the per-session CSRF token | role check is central in dispatch() |
| /admin, /admin/users, /admin/settings, /admin/backup, /admin/backup/download, /admin/audit | admin | session cookie + admin role + CSRF token on POST | backup download hands out the whole database |
| ./run.sh, ./run.sh demo, backup and restore commands | local | operating-system account | read and write the data directory |
| Automatic backup thread | local | n/a | writes to the backup folder on start and every 24 h |

### Assets

| asset | kind | where |
|---|---|---|
| Families' and pupils' personal data (names, addresses, phone, email, dates of birth) | personal data | data/lessonledger.db and backups |
| Invoices, payments, credit notes, refunds | money / record integrity | data/lessonledger.db |
| Staff password hashes and session tokens | secrets | users and sessions tables |
| Session secret | secrets | meta table in data/lessonledger.db |
| Service availability | availability | the single Python process |

## What was checked, and how

The product was started as its README says and probed while running.

| area | check | result | evidence |
|---|---|---|---|
| authN/authZ | anonymous GET of all 25 non-public routes | pass | every one redirects 303 to /login?next=... |
| authN/authZ | anonymous POST to /terms, /directory/rooms/new, /admin/users, /logout | pass | redirected to /login, nothing saved |
| authN/authZ | staff user GET of /admin, /admin/users, /admin/settings, /admin/backup, /admin/backup/download, /admin/audit | pass | all 403 |
| authN/authZ | staff user POST to /admin/users (demote owner) and /admin/settings | pass | 403; owner still admin, settings unchanged |
| authN/authZ | staff voiding an invoice when void_permission=admin_only | pass | enforced in core.py:1347 (code review; not driven end to end) |
| authN/authZ | setup only from loopback | pass | is_local() checks the socket peer address, not a header (web.py:220) |
| hostile HTTP | negative Content-Length (-1) on POST /login | fail | server read 100 MiB until the client closed; process max RSS 31 MiB -> 302 MiB; then answered 200 |
| hostile HTTP | non-numeric Content-Length (abc) | fail | no response, connection dropped; ValueError traceback printed to the server's stderr |
| hostile HTTP | huge Content-Length (99999999999) | pass | 413 at once |
| hostile HTTP | body larger than the 2 MB limit | pass | 413 before reading (limit checked on Content-Length) |
| hostile HTTP | malformed / 20,000-level nested JSON body | pass | the app reads only form-encoded bodies; treated as an empty form, 200 login page |
| hostile HTTP | huge id (99999999999999999999999) and non-numeric id in URL | pass | 303/404, no 500 |
| hostile HTTP | huge, negative, NaN, Infinity values in numeric fields | not_checked | budget; amounts are parsed by core validators into integer minor units |
| injection | SQL injection: ' OR 1=1 -- in family name, search q=, and URL ids | pass | all queries use ? placeholders; table names come from a fixed whitelist; values stored literally |
| injection | stored XSS: <script> in teacher name, family name/address/notes, user display name; viewed on lists, family page, admin users, audit log | pass | escaped everywhere checked (html.escape) |
| injection | reflected XSS in q= and login next= | pass | escaped |
| injection | CSRF: POST with a wrong token | pass | 403 'This form has expired' |
| injection | CSRF: POST with a valid token and a foreign Origin | pass | accepted (303), but an attacker site cannot read the token, so the token alone protects it; cookie is also SameSite=Strict |
| injection | CSRF on /setup and /login (no token) | fail | both public forms accept cross-site POSTs; see S6, below |
| injection | open redirect via next= on login | fail | //evil.com and https://evil.com are refused, but /\evil.com is passed through as Location: /\evil.com |
| injection | path traversal | n/a | no route takes a file name or path; the restore command takes a path from the local operator only |
| authentication | lockout after repeated wrong passwords | pass | after 5 failures the 6th attempt and the right password both get 'locked' |
| authentication | session cookie flags | pass | ll_session=...; HttpOnly; SameSite=Strict; Path=/ (no Secure, acceptable for plain-HTTP LAN/localhost) |
| authentication | session ends on logout | pass | end_session deletes the session row (core.py:458) |
| authentication | other sessions end on password change | fail | a second session opened before the change still loads the dashboard afterwards |
| authentication | sessions end on deactivation and admin password reset | pass | DELETE FROM sessions in core.py:368 and :383 (code review) |
| authentication | password storage | pass | pbkdf2-sha256, 120,000 iterations, random 16-byte salt per user |
| authentication | user enumeration by timing on login | pass | unknown usernames still run a hash (core.py:406) |
| secrets and defaults | default credentials and hard-coded secrets (grep for password/secret/token literals) | pass | none found; session secret is random on first run (db.py:173); demo users get random printed passwords and must change them |
| secrets and defaults | secrets in logs | pass | no log call writes passwords or tokens; errors log method + path + traceback only |
| secrets and defaults | file permissions of database and backups | fail | lessonledger.db, -wal, -shm and backup files are 0644; data dir 0775 |
| dependencies | third-party dependencies | n/a | standard library only; no requirements file or pyproject |
| error pages | 500 page content (triggered by POST /admin/users with a missing user field) | pass | generic 'Something went wrong ... logged at <time>' page; no traceback, path or SQL. The KeyError itself is a small robustness bug in an admin-only form |
| error pages | Server header | pass | reveals 'LessonLedger Python/3.12.3' version; informational only |

## Findings

| | severity | finding | status |
|---|---|---|---|
| S1 | high | A negative Content-Length makes the server read the request body with no size limit | fixed (a test checks it) |
| S2 | medium | The login page can redirect to another website with next=/\evil.example | fixed (a test checks it) |
| S3 | medium | Changing your password does not sign out your other sessions | fixed (a test checks it) |
| S4 | low | A non-numeric Content-Length crashes the request handler with no response | its test passes after other fixes; confirm by hand |
| S5 | low | The database and backups are readable by every account on the office computer | open |
| S6 | low | The setup and login forms have no CSRF protection | open |

### S4 (low): A non-numeric Content-Length crashes the request handler with no response

- Where: lessonledger/web.py:1252
- What happens: empty reply, connection closed; ValueError traceback on the server's stderr (outside the app's own error handler and log)
- What should happen: 400 Bad Request
- Reproduce: `printf 'POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n' \| nc 127.0.0.1 8080`
- Test: `tests/acceptance/test_non_numeric_content_length_gets_400_response_instead.py` passes since other fixes went in, but this finding wasn't repaired on its own: a changed default can also void the test's premise. Reproduce it by hand before closing it.

### S5 (low): The database and backups are readable by every account on the office computer

- Where: lessonledger/db.py:156, lessonledger/db.py:191
- What happens: lessonledger.db, its -wal/-shm files and backup files are mode 0644 (data dir 0775). They hold families' personal data, password hashes, live session token hashes and the session secret.
- What should happen: data directory 0700 and files 0600 (or an umask of 077 when the service creates them)
- Reproduce: `./run.sh; ls -l data data/backups`
- Test: `tests/acceptance/test_database_backups_readable_only_account_runs_service.py` (marked as a known open item)

### S6 (low): The setup and login forms have no CSRF protection

- Where: lessonledger/web.py:228, lessonledger/web.py:264
- What happens: before the owner finishes setup, a web page opened in a browser on the server computer could POST to http://127.0.0.1:8080/setup and create the owner account with the attacker's password (the request comes from loopback, so is_local passes). Login CSRF can sign a user into an attacker-chosen account. Both need the victim to browse a hostile site at the right moment.
- What should happen: setup and login refuse POSTs whose Origin/Referer is another site, or carry a pre-session token
- Reproduce: `code review: both routes are role='public', so dispatch() skips the CSRF token check, and neither checks Origin`

## Dependency audit

- Tool: pip-audit; result: no_dependencies.
- The product uses only the Python standard library (README; no requirements.txt or pyproject.toml), so there is nothing for pip-audit to check. Keep the Python interpreter itself patched.

## Known limits

- This was a time-boxed review of v1 by one reviewer with the code and a running copy: scripted probes and manual checks, not a penetration test or an external audit.
- TLS is not provided by the product; LAN traffic, including passwords, is plain HTTP unless the operator adds a reverse proxy. Not tested.
- Huge, negative, NaN and Infinity values in money and duration fields were not sent; no SQL or XSS tests were run on every single form field, only a representative set.
- Restore command, demo command and the auto-backup thread were reviewed only for file permissions, not attacked with crafted backup files.
- Slow-request (slowloris) behaviour and many concurrent connections were not measured; the server uses one thread per connection with no timeout.
- Voiding permission and session expiry were checked by reading the code, not end to end.

## Reporting a security issue

Please report security problems privately, not in a public issue: use the repository host's private vulnerability reporting (on GitHub: Security, then Report a vulnerability), or write to the maintainers directly. Include the version, the steps to reproduce and what an attacker could do. You will get an answer within a few working days.
