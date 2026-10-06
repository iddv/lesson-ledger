# Scope: Lesson Ledger

Lesson Ledger is a timetable and term-billing system for a small music school, installed on one office computer and used by staff from a browser on the local network. The school's office runs it. In v1 staff can:

- keep the school's teachers, families, pupils, rooms and lesson types;
- lay out each term's weekly timetable, which refuses any lesson that would double-book a room, teacher or pupil and says why;
- set the term's skipped weeks and cancel single lessons;
- at term end, produce one printable invoice per family, record payments and corrections, and export the term's figures;
- back up and restore all data with one action.

## Users

- **Owner (admin):** the school owner or office manager. Needs everything staff need, plus managing staff accounts, settings, voiding invoices (see `invoices.void_permission`) and backups. The first owner account is created on first run (F1). Any admin can make other users admin, but the last active admin cannot be demoted or deactivated.
- **Office staff:** front-desk and administration people. They keep records, build timetables, generate and issue invoices, and record payments. They sign in with a username and password that an admin creates.
- **Teachers, families and pupils** are records only and have no login in v1.

## Core flows

### F1: Install and first run
- Who: Owner
- Steps:
  1. The owner follows the README on a fresh machine and runs the single install-and-start command.
  2. The service starts on 127.0.0.1:8080 **(default)** with an empty database and prints the address to open.
  3. The owner opens the address in a browser on the same machine. Because no user exists, the system shows the setup screen. The owner enters the school name, address, currency, time zone, and their own username and password, twice.
  4. The system validates the input, creates the owner account and the school settings, and signs the owner in.
  5. The owner sees the main screen: an empty dashboard with links to Directory, Terms, Timetable, Invoices, Payments, Reports and Admin, and a hint naming the demo command.
  6. To share on the LAN, the owner sets the listen address as documented in the README and restarts. To try the product, the owner runs the documented demo command, which works only on an empty database.
- When it goes wrong:
  - Setup screen opened from another machine: it refuses with "Setup must be completed on the server computer."
  - Weak password (see rules) or the two passwords differ: the field is marked and the error is shown.
  - Port already in use: the service exits with a message naming the port and the setting that changes it.
  - Demo command run on a database that has data: it refuses and changes nothing.

### F2: Manage staff accounts
- Who: Admin; any user for their own password
- Steps:
  1. The admin opens Admin → Users and adds a user: username, display name, role (admin or staff) and a temporary password.
  2. The system records the user and flags the password as must-change. On first login the user must set a new password.
  3. The admin can edit the name and role, reset a password (again must-change), or deactivate or reactivate a user.
  4. Any user can change their own password and sign out.
- When it goes wrong:
  - Duplicate username: "Username already taken."
  - Demoting or deactivating the last active admin is refused.
  - Wrong password: "Invalid username or password." After 5 failures the account is locked for 15 minutes **(default)**.
  - A deactivated user cannot log in, and any open sessions they have end.

### F3: Keep the directory
- Who: Staff
- Steps:
  1. Staff create and edit each kind of record:
     - **Teachers:** name, phone, email, colour.
     - **Rooms:** name, notes.
     - **Lesson types:** name, e.g. "Piano 30"; duration in minutes; price per lesson; maximum pupils (1 for individual lessons).
     - **Families:** billing name, address, email, phone, notes.
     - **Pupils:** name, date of birth (optional), instrument, family; every pupil belongs to exactly one family.
  2. Each list has search by name and filters for active or archived.
  3. A family page shows its pupils, their weekly lessons and all of the family's invoices with balances.
  4. Staff archive a record. It disappears from pickers but stays on history and invoices, and can be restored.
- When it goes wrong:
  - Missing or invalid field (e.g. price not a positive amount, duration outside 15–120 min): a field-level error and nothing is saved.
  - Duplicate room or lesson type name: refused.
  - Archiving a teacher, room, pupil or lesson type that has slots in the current or a future term: refused, with a list of those slots to end first.
  - Hard delete is only possible for records never used in a slot or invoice.
  - Another user saved the same record first: "This record changed since you opened it," and the newer values are shown.

### F4: Set up a term
- Who: Staff
- Steps:
  1. Staff create a term: name (e.g. "Autumn 2026"), first day and last day.
  2. Staff add skipped dates, either a single day or a range, each with a label (e.g. "Half-term 26–30 Oct", "Bank holiday").
  3. The term page shows each teaching week and, for every weekday, the number of teaching days.
  4. Staff may copy the timetable from a previous term. All slots that pass the conflict checks are created, and the rest are listed with reasons.
  5. Staff can edit the dates and skipped dates until invoices exist for the term, then close the term once all its invoices are paid or void.
- When it goes wrong:
  - The last day is before the first day, or the term overlaps another term: refused with the clashing term named.
  - A skipped date outside the term: refused.
  - Changing dates or skipped dates after invoices exist: refused with "Void the term's invoices first."

### F5: Build the weekly timetable
- Who: Staff
- Steps:
  1. Staff pick a term and see the week grid, with times by weekday and a column per room. They can switch the view to by-teacher.
  2. Staff add a slot: weekday, start time, lesson type (which sets the duration), teacher, room, one or more pupils (up to the type's maximum), start date and end date (default: the whole term).
  3. The system checks the conflict rules and saves the slot only if there is no conflict.
  4. Staff can edit a slot: move the time, room or teacher, add or remove pupils, or change the date range. Every edit is re-checked.
  5. Staff can end a slot from a date (e.g. a pupil leaves mid-term), or delete a slot that has no occurrences on an issued invoice.
  6. Staff print the week for a room or a teacher, or the whole school.
- When it goes wrong:
  - Conflict: the slot is refused with one line per clash, e.g. "Room 2 is booked Tue 16:00–16:30 by Piano 30 (Mr Jones, Anna Smith)." Nothing is saved.
  - More pupils than the type allows: refused.
  - Archived pupil, teacher, room or type selected: refused.
  - Outside opening hours: refused.
  - Changing a slot whose occurrences are already on an issued invoice: allowed only from a date after the invoiced period, otherwise "Issue a credit note instead."

### F6: Cancel or restore a single lesson
- Who: Staff
- Steps:
  1. From the timetable, staff open the term's dated lesson list (filterable by teacher, room, pupil or date) and pick one occurrence.
  2. They choose an action:
     - "Cancelled by school" (not charged), with a reason;
     - "Pupil absent", charged or not per `billing.pupil_absence`;
     - "Restore".
  3. The occurrence shows its status everywhere, and invoice drafts pick it up.
- When it goes wrong:
  - The date is a skipped date or outside the slot's range: no such occurrence exists.
  - The occurrence is on an issued invoice: refused with "Issue a credit note instead."

### F7: Generate, review and issue term invoices
- Who: Staff; voiding per setting
- Steps:
  1. Staff open Invoices for a term and click "Generate drafts". The system creates one draft per family with chargeable lessons. Each line is one pupil and slot: "Anna – Piano 30 – Tue 16:00 – 11 lessons × £21.00 = £231.00". Lesson counts follow the billing rules.
  2. Staff review the drafts list (family, total, number of lines) and open any draft. They can add a manual adjustment line, positive or negative, with a description (e.g. "Sibling discount"), or remove an adjustment they added.
  3. "Regenerate" rebuilds the computed lines of drafts from the current timetable and keeps the manual adjustments.
  4. Staff issue one draft or all of them. Each gets the next invoice number, an issue date and a due date, and is frozen.
  5. Each issued invoice has a printable page and a print-all view for the term. The page shows the school details, family, number, dates, lines with lesson dates listed, total, paid and balance due, and the term's skipped dates.
  6. To correct an issued invoice, staff create a credit note against it (lines and reason) or, if allowed, void it with a reason and regenerate a new draft for that family.
- When it goes wrong:
  - Generating twice: existing drafts and issued invoices are kept, and only families without a non-void invoice get new drafts.
  - Issuing a draft with a total of 0 or less: refused.
  - A credit note larger than the remaining invoice total: refused.
  - Voiding an invoice that has payments: refused until the payments are reversed or refunded.
  - Staff voiding when the setting is admin-only: "Only an admin can void invoices."

### F8: Record payments, refunds and corrections
- Who: Staff
- Steps:
  1. From an issued invoice or the family page, staff record a payment: amount (prefilled with the balance), date (default today), method (cash, bank transfer, card, cheque, other) and an optional reference.
  2. "Mark paid" records one payment equal to the balance in a single click, after asking for the method.
  3. The invoice status updates (issued → part-paid → paid), and the balance and family page refresh.
  4. Staff reverse a mistaken payment with a reason. This records a negative entry and leaves the original in place.
  5. When credits leave the paid amount above the total, staff record a refund (amount, method, date) up to the overpaid amount.
- When it goes wrong:
  - Amount of zero or less, or a date in the future: refused.
  - Payment above the balance: refused when `payments.overpayment` = reject, otherwise kept as family credit.
  - Payment on a draft or void invoice: refused.
  - Refund above the overpaid amount: refused.
  - Two staff paying the same invoice at once: the second payment is re-checked against the new balance and refused if it would overpay.

### F9: Term and payments reports
- Who: Staff
- Steps:
  1. **Term billing report:** staff pick a term. Per family it shows invoiced, credited, paid, refunded and outstanding amounts, with totals and a count of overdue invoices.
  2. **Payments report:** staff pick a date range (default the current month). It lists each payment, reversal and refund with totals per method and per day.
  3. **Teacher lesson report:** for a term, the number of delivered and cancelled lessons per teacher.
  4. Every report can be printed and downloaded as CSV.
- When it goes wrong:
  - The date range ends before it starts, or is longer than 366 days: refused.
  - No data: the report shows an empty state with zero totals.

### F10: Back up and restore
- Who: Admin
- Steps:
  1. The admin clicks Admin → Backup → "Download backup" and receives one consistent file containing all data, settings and the schema version. The same action is also available as a documented command.
  2. On each start and every 24 h, the system writes an automatic backup to the backup folder and keeps the newest 14 **(default)**.
  3. To restore, the admin stops the service and runs the documented restore command with a backup file. The system checks the file, keeps a copy of the current data, replaces it, and runs migrations if the backup is older.
  4. After restart, the data matches the backup.
- When it goes wrong:
  - Corrupt or foreign file: refused and the current data is untouched.
  - Backup from a newer version: refused with the version numbers.
  - Backup folder not writable: an error is logged and shown as a banner on the admin dashboard.

## Features
### Must have (v1)
- M1: Single-command install, localhost-only first-run setup, empty start, explicit demo data command (F1)
- M2: Username/password login, admin and staff roles, must-change temporary passwords, lockout, deactivation (F2)
- M3: Directory of teachers, rooms, lesson types, families and pupils with search, edit, archive and restore, plus a family overview page (F3)
- M4: Terms with skipped dates and ranges, teaching-day counts, copy timetable from a previous term, closing (F4)
- M5: Weekly timetable with room, teacher and pupil conflict checks that name each clash, group lessons, mid-term start and end, and printable views (F4, F5)
- M6: Per-occurrence cancellation by school and pupil absence (F6)
- M7: Draft generation of one invoice per family per term, adjustment lines, issuing with sequential numbers, printable invoices, credit notes and voiding (F7)
- M8: Payments, one-click mark paid, reversals and refunds with live balances and statuses (F8)
- M9: Term billing, payments and teacher lesson reports with print and CSV export (F9)
- M10: Audit log of every money, invoice, timetable and user change, viewable by admins and filterable by record and date (F2, F5–F8)
- M11: Backup download and command, automatic rotating backups, restore command, versioned migrations (F10)
- M12: Operator settings screen for the switches below, and an automated test suite run by one command (F1–F10)

### Later (not in v1)
- Teacher, parent or pupil logins and portals: the office runs everything in v1.
- Emailing invoices or reminders: printing covers v1, and email needs mail setup.
- Online card payments and bank feed import: payments are recorded manually.
- Teacher pay and payroll: this is a separate money domain.
- Automatic sibling or multi-lesson discount rules: manual adjustment lines cover them.
- Tax/VAT lines: music tuition is often exempt, so this can wait for a school that needs it.
- Teacher availability and auto-scheduling: conflict checking is the v1 need.
- Multi-school or hosted multi-tenant use: one school per install.
- Make-up lesson tracking: cancel and credit covers money correctness.

## Domain rules and defaults
- **Time:** the school time zone is chosen at setup, defaulting to the server's time zone **(default)**. Weeks run Monday to Sunday.
- **Opening hours:** 07:00–22:00 **(default)**. Start times are on 5-minute steps.
- **Lesson types:** duration 15–120 minutes. Maximum pupils is 1–12, default 1 **(default)**. The price is per pupil per lesson.
- **Conflict:** two slots in the same term conflict when all of these hold:
  - they share a room, a teacher or a pupil;
  - they fall on the same weekday;
  - their time ranges overlap; end times are exclusive, so 16:00–16:30 and 16:30–17:00 do not conflict;
  - their date ranges overlap.

  Each clash is reported separately.
- **Occurrences:** a slot's occurrences are its weekday's dates within both the term and the slot's own date range, minus the term's skipped dates.
- **Chargeable lessons:** occurrences minus "cancelled by school" ones, minus "pupil absent" ones when `billing.pupil_absence` = no_charge.
- **Line amount:** lessons × price at the time of generation. The price is copied onto the line, so later price changes don't alter drafts already generated until they are regenerated.
- **Families with no chargeable lessons** get no invoice.
- **Invoice numbers:** `<YEAR>-<0001>` **(default)**. They are sequential with no gaps among issued invoices, are assigned at issue, are never reused, and void invoices keep their number.
- **Due date:** issue date + 14 days **(default)**. An invoice is overdue if its balance is above 0 after the due date.
- **Invoice balance:** total − credit notes − payments + reversals + refunds.
- **Invoice status:** draft, issued (balance = total), part-paid, paid (balance ≤ 0), void.
- **Passwords:** at least 10 characters **(default)**. Sessions expire after 8 hours idle **(default)**.
- **Audit retention:** audit entries and money entries are kept forever.

## Operator settings

| key | values | default | what it decides |
|---|---|---|---|
| `billing.pupil_absence` | charge, no_charge | charge | Whether lessons marked "pupil absent" are billed. |
| `payments.overpayment` | reject, allow_credit | reject | Whether a payment above the balance is refused or kept as family credit applied to that family's next issued invoice. |
| `invoices.void_permission` | admin_only, any_staff | admin_only | Who may void an issued invoice. |
| `timetable.copy_pupils` | copy, empty | copy | Whether copying a timetable to a new term keeps the pupils on each slot or copies only the room, teacher and time. |

## Money and data integrity
- **Amounts:** stored as integer minor units (cents/pence), never floats. There is one currency per install, chosen at setup, GBP **(default)**. Adjustment amounts are entered to the cent, so no rounding is needed elsewhere.
- **Entries are immutable:** issued invoice lines, credit notes, payments, reversals and refunds are never edited or deleted. Corrections are always new entries with a reason, user and timestamp. Voiding keeps the invoice and all its lines.
- **Derived figures:** every balance, status and report total is computed from or reconciled to the sum of entries. The test suite checks that report totals equal the sum of invoice balances.
- **No double billing:** at most one non-void invoice per family per term, enforced in storage. Generation is safe to repeat.
- **Simultaneous edits:**
  - Slot saves run the conflict check and the save in one transaction, so two staff booking the same room at once cannot both succeed.
  - Record edits carry a version; a stale save is refused (F3).
  - Payments re-check the balance inside the transaction.
- **Validation:** all input is validated on the server before anything is saved. A failed request saves nothing.

## Install and run
- **One command** installs dependencies and starts the service on a fresh machine, as documented in the README. A second documented way runs it as a background service that starts with the computer.
- **Safe defaults:**
  - The service listens on 127.0.0.1:8080. LAN access requires setting the listen address explicitly.
  - A fresh install is empty.
  - The owner account is created only through the localhost setup screen, with an operator-chosen password.
  - There are no default passwords and no built-in secrets. The session secret is generated randomly on first run and stored with the data.
- **Demo data** loads only via the explicit demo command on an empty database. It contains:
  - 6 teachers, 5 rooms, 6 lesson types including one group type of 8;
  - 40 families and 60 pupils;
  - a past term with issued invoices, some paid, part-paid, credited and one voided;
  - a current term with a half-term and a bank holiday, about 90 slots and a few cancelled lessons;
  - demo users `admin` and `staff`, each with a printed random password.
- **Configuration** is through environment variables or a config file, all documented in the README: listen address and port, data directory, backup directory, backup retention count, and log level.
- **Data location:** all data lives in one data directory. Back it up and restore it as in F10. The schema is versioned, migrations run automatically on start, and a backup is taken before any migration.

## Non-functional basics
- **Roles:** admin can do everything. Staff can do everything except user management, settings, backup/restore, viewing the audit log, and voiding when the setting is admin-only. Every page and action requires login.
- **Errors:** clear field-level messages in plain words. Server errors are logged, and the user sees a generic message with a time.
- **Persistence:** data survives restarts and power loss without partial writes.
- **Audit trail:** M10 covers who, when, what changed, and the before and after values.
- **Printing:** invoice and timetable pages print cleanly on A4 and Letter.
- **Tests:** an automated suite run by one documented command covers:
  - conflict detection, including back-to-back slots and date-range edge cases;
  - occurrence counting with skipped dates;
  - invoice generation idempotence;
  - balances under payments, reversals, credits and refunds;
  - permissions;
  - backup and restore round-trip.

## Definition of done
- [ ] F1: Install and first run — on a fresh machine, the one README command starts the service, the localhost setup creates the owner, and the owner sees an empty dashboard. The demo command then fills it, and is refused on a non-empty database.
- [ ] F2: Manage staff accounts — an admin creates a staff user who must change the temporary password at first login. The 6th wrong password locks the account, and the last admin cannot be demoted.
- [ ] F3: Keep the directory — teachers, rooms, lesson types, families and pupils can be created, searched, edited, archived and restored. Archiving a teacher with current slots is refused with the slot list.
- [ ] F4: Set up a term — a term with a half-term range shows correct teaching-day counts per weekday, and copying a previous timetable reports the slots it skipped and why.
- [ ] F5: Build the weekly timetable — a slot clashing on room, teacher or pupil is refused with each clash named, a back-to-back slot is accepted, and the printed room view shows the week.
- [ ] F6: Cancel or restore a single lesson — a "cancelled by school" lesson drops off the family's regenerated draft, and restoring it brings it back.
- [ ] F7: Generate, review and issue term invoices — generating twice yields one invoice per family. Issued invoices get gapless numbers, print with lesson dates and skipped dates, and accept credit notes.
- [ ] F8: Record payments, refunds and corrections — mark paid sets the balance to 0 and the status to paid, a reversal restores the balance, and an overpayment is refused under the default setting.
- [ ] F9: Term and payments reports — the term report totals equal the sum of the invoices, the payments report totals per method match the entries, and both download as CSV.
- [ ] F10: Back up and restore — a downloaded backup restored onto a fresh install reproduces all records, invoices and balances, and a corrupt file is refused with the data untouched.
