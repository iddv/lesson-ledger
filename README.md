# Lesson Ledger

Timetable and term billing for a small music school. It runs on one office computer, and staff
use it from a browser on the local network.

## At a glance

- **What it is:** A self-hosted browser app that lets a small music school build a clash-free weekly lesson timetable and turn each term into one printable invoice per family.
- **Who it's for:** Office staff at small independent music schools who currently juggle lessons, rooms and term invoices across spreadsheets on one office computer.
- **Quick start:**

  ```sh
  git clone https://github.com/iddv/lesson-ledger.git
  cd lesson-ledger
  # then follow the install section below
  ```

The rest of this README covers configuration, data, backup and the full guide; SECURITY.md and READINESS.md say what was checked before this release.

It is written in Python using only the standard library, and stores its data in SQLite.
There is nothing extra to download: the program has no third-party dependencies, so there is
nothing to pin or lock (pytest is only needed for the optional acceptance tests).

## Install and start (one command)

You need **Python 3.9 or newer** (it comes with most Linux distributions and macOS; on Windows
install it from python.org, or use WSL). Copy this folder to the computer, then run this inside it:

```sh
./run.sh
```

`run.sh` checks the Python version and starts the service on **http://127.0.0.1:8080**. It
prints the address to open. The first time you open that address **on the same computer**, you
get the setup screen. Enter the school name, address, currency, time zone, and your owner
username and password (twice, at least 10 characters). Setup is refused from any other
computer.

If the port is already in use, the service stops with a message that names the port. Set
`LL_PORT` (or `port` in the config file) to use a different one.

Stop the service with Ctrl+C.

## Try it with demo data

The demo command only works on an empty database. That means no directory records, terms or
invoices yet; finishing setup first is fine. Stop the service, then run:

```sh
./run.sh demo
./run.sh
```

It creates 6 teachers, 5 rooms, 6 lesson types (one is a group lesson for up to 8 pupils), 40
families and 60 pupils. It also adds:

- a past term with issued invoices: paid, part-paid, credited and one voided;
- a current term with a half-term and a bank holiday, 90 slots and some cancelled lessons;
- the users `admin` and `staff`, with random passwords printed on screen. Both must change
  their password at first sign-in.

## Configuration

Settings are read from `lessonledger.conf` in the folder you start from (copy
`lessonledger.conf.example`), or from the file named by `LL_CONFIG`. Environment variables
override the file:

| Variable | Config key | Default | Meaning |
|---|---|---|---|
| `LL_HOST` | `host` | `127.0.0.1` | Listen address. Use `0.0.0.0` (or the computer's LAN IP) for LAN access. |
| `LL_PORT` | `port` | `8080` | Listen port. |
| `LL_DATA_DIR` | `data_dir` | `./data` | Holds all data: the database, session secret and settings. |
| `LL_BACKUP_DIR` | `backup_dir` | `<data_dir>/backups` | Folder for automatic backups. |
| `LL_BACKUP_KEEP` | `backup_keep` | `14` | Number of automatic backups to keep. |
| `LL_LOG_LEVEL` | `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

### Sharing on the local network

By default only the computer itself can connect. To let other office computers use it, start
it with:

```sh
LL_HOST=0.0.0.0 ./run.sh
```

You can also set `host = 0.0.0.0` in `lessonledger.conf` and restart. Staff then open
`http://<this-computer's-IP>:8080/`. You may need to allow the port through the computer's
firewall.

Business settings live in the app under **Admin → Settings**. These include school details,
opening hours, invoice due days, password rules, and the four switches: `billing.pupil_absence`,
`payments.overpayment`, `invoices.void_permission` and `timetable.copy_pupils`.

### Business rule settings

These switches are set on **Admin → Settings**. Each one has a single value for the whole
school. If you set its environment variable to one of the allowed values, that value wins
everywhere and is read on every use. Values that aren't allowed are ignored.

| Key | Values | Default | What each value does | Scope | Environment variable |
|---|---|---|---|---|---|
| `timetable.end_within_hours` | `start_only`, `whole_lesson` | `whole_lesson` | `whole_lesson`: a slot is accepted only if it starts and ends within opening hours. `start_only`: a slot is accepted if its start time is within opening hours, even if it runs past closing. | whole system | `TIMETABLE_END_WITHIN_HOURS` |
| `invoices.number_year` | `issue_date`, `term_start` | `issue_date` | `issue_date`: the year in the number (`<YEAR>-0001`) is the year the invoice is issued. `term_start`: it is the year the invoice's term starts. Either way, each year has its own gapless sequence starting at 0001. | whole system | `INVOICES_NUMBER_YEAR` |
| `directory.archive_family_with_active_pupils` | `allowed`, `refused` | `refused` | `refused`: archiving a family is refused while any of its pupils has slots in the current or a future term, and the refusal lists those slots to end first. `allowed`: a family can be archived whatever its pupils have booked. | whole system | `DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS` |
| `payments.before_issue_date` | `allowed`, `refused` | `allowed` | `allowed`: any payment date up to today is accepted, for example money received in advance. `refused`: a payment dated before the invoice's issue date is refused with a field error on the date. | whole system | `PAYMENTS_BEFORE_ISSUE_DATE` |

## Run as a background service (starts with the computer)

On Linux with systemd:

```sh
sudo cp -r . /opt/lessonledger
sudo cp lessonledger.service /etc/systemd/system/
sudo nano /etc/systemd/system/lessonledger.service   # set User=, and LL_HOST if you want LAN access
sudo systemctl daemon-reload
sudo systemctl enable --now lessonledger
journalctl -u lessonledger -f                        # see the log
```

On macOS, use a LaunchAgent that runs `/path/to/run.sh serve`. On Windows, use Task Scheduler
"At startup" running `python -m lessonledger serve` in the folder.

## Backups and restore

- **Automatic:** a backup is written to the backup folder when the service starts and every
  24 hours. The newest 14 are kept. If the folder can't be written, the error is logged and
  shown as a banner on the admin pages.
- **Download:** go to Admin → Backup → **Download backup**. You get one consistent file with all
  data, settings and the schema version.
- **Command:** `./run.sh backup` writes a backup to the backup folder. `./run.sh backup FILE`
  writes it to `FILE` instead. This works while the service is running.
- **Restore:** stop the service, then run:

  ```sh
  ./run.sh restore path/to/backup.db
  ./run.sh
  ```

  Restore first checks the file. A corrupt or foreign file, or a backup from a newer version,
  is refused and your data is left untouched. Before replacing anything, it keeps a copy of
  the current data as `data/pre-restore-<time>.db`. A backup from an older version is
  migrated automatically.

The schema is versioned. Pending migrations run automatically at start, and a backup
(`pre-migration-*`) is taken before them.

## Upgrading

1. Make a backup first: `./run.sh backup` (or Admin → Backup → **Download backup**).
2. Stop the service (Ctrl+C, or `sudo systemctl stop lessonledger`).
3. Replace the program files (`run.sh`, `lessonledger/` and the rest of this folder) with the
   new version. Keep your `data/` folder and your `lessonledger.conf`.
4. Start it again (`./run.sh`, or `sudo systemctl start lessonledger`). Any database changes
   the new version needs are applied automatically at start, after a `pre-migration-*`
   backup is written to the backup folder.

To go back to the old version, put the old program files back and restore the backup you
made in step 1 with `./run.sh restore FILE`.

## Troubleshooting

- **"Python 3.9 or newer is required"**: install a newer Python 3 and run `./run.sh` again.
  You can point to a specific interpreter with `PYTHON=/path/to/python3 ./run.sh`.
- **The port is already in use**: another program (or another copy of Lesson Ledger) is using
  port 8080. Stop it, or start on another port: `LL_PORT=8090 ./run.sh`.
- **Other computers can't connect**: by default only this computer can connect. Set
  `LL_HOST=0.0.0.0` (see *Sharing on the local network*) and allow the port through the
  firewall.
- **"Setup must be completed on the server computer"**: open the address in a browser on the
  computer that runs Lesson Ledger, for example `http://127.0.0.1:8080/`.
- **An account is locked**: after 5 wrong passwords the account is locked for 15 minutes.
  Wait, or ask an admin to reset the password under Admin → Users.
- **The admin pages show a backup error banner**: the backup folder can't be written. Check
  that it exists and that the account running the service may write to it, or set
  `LL_BACKUP_DIR` to another folder.
- **"Something went wrong" with a time**: the details are in the service's log (the terminal
  it runs in, or `journalctl -u lessonledger`). Set `LL_LOG_LEVEL=DEBUG` for more detail.
- **The demo command refuses**: it only works on an empty database. Use a fresh data folder,
  for example `LL_DATA_DIR=demo-data ./run.sh demo` then `LL_DATA_DIR=demo-data ./run.sh`.

## Known limitations

- One school per install, and one currency.
- Teachers, families and pupils have no login; only office staff and admins sign in.
- Invoices are printed from the browser; there is no email sending.
- Payments are recorded by hand; there are no online card payments or bank imports.
- No tax/VAT lines, no automatic discounts (use adjustment lines), no make-up lesson tracking,
  no teacher pay.
- The service speaks plain HTTP. Use it only on a trusted office network, or put it behind a
  reverse proxy that adds HTTPS.
- The database is a single SQLite file; it is meant for one office computer, not for many
  servers sharing the data.

## Tests

```sh
./run.sh test
```

This runs the unit and HTTP tests with Python's built-in test runner; nothing extra is needed.

If a `tests/acceptance` folder is present, it holds end-to-end acceptance tests that need
pytest. Install pytest (the CI uses `pytest==8.3.3`; inside a virtual environment if your
system Python doesn't allow it) and run them from this folder:

```sh
python -m pytest tests/acceptance
```

The tests cover conflict detection (including back-to-back slots and date-range edges),
occurrence counting with skipped dates, idempotent invoice generation, gapless numbering,
balances under payments, reversals, credit notes and refunds, report totals, permissions,
lockout, the last-admin rule, stale edits, backup/restore round trip and corrupt-file refusal,
demo data, and an HTTP walk through every page as staff and as admin.

## Layout

- `lessonledger/core.py`: domain rules (conflicts, occurrences, billing, payments, reports, audit)
- `lessonledger/db.py`: configuration, schema, migrations, backup and restore
- `lessonledger/web.py`: HTTP server and pages
- `lessonledger/demo.py`: demo data
- `tests/`: automated tests

Money is stored as integer pence/cents. Issued invoice lines, credit notes, payments, reversals,
refunds and audit entries can't be changed in storage (database triggers enforce this). A
unique index allows at most one non-void invoice per family per term.
