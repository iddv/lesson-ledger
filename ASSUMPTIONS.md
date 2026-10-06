# Assumptions

The idea this product was built from leaves these questions open. Each section says what this version does.

The rules and numbers the idea left open are set as defaults in the product scope, `SCOPE.md` (each marked *(default)*).

## Settings

Where reasonable operators differ between two business policies, the operator chooses. Each setting below exists in this version; the README's configuration section says how to change it, and the environment variable named below overrides it everywhere.

| key | values | default | scope | settles |
|---|---|---|---|---|
| `timetable.end_within_hours` | start_only, whole_lesson | `whole_lesson` | global | Must a lesson end by closing time, or only start within opening hours? |
| `invoices.number_year` | issue_date, term_start | `issue_date` | global | Which year goes into the invoice number, and does the sequence restart each year? |
| `directory.archive_family_with_active_pupils` | allowed, refused | `refused` | global | May a family be archived while it still has active pupils or unpaid invoices? |
| `payments.before_issue_date` | allowed, refused | `allowed` | global | May a payment be dated before the invoice's issue date (e.g. money received in advance)? |

- `timetable.end_within_hours` (`TIMETABLE_END_WITHIN_HOURS`): `start_only`: a slot is accepted if its start time is within opening hours; `whole_lesson`: a slot is accepted only if it starts and ends within opening hours.
- `invoices.number_year` (`INVOICES_NUMBER_YEAR`): `issue_date`: the number's year is the year the invoice is issued; `term_start`: the number's year is the year the term starts.
- `directory.archive_family_with_active_pupils` (`DIRECTORY_ARCHIVE_FAMILY_WITH_ACTIVE_PUPILS`): `allowed`: a family can be archived regardless of its pupils; `refused`: archiving is refused while any of its pupils has slots in the current or a future term.
- `payments.before_issue_date` (`PAYMENTS_BEFORE_ISSUE_DATE`): `allowed`: any payment date up to today is accepted; `refused`: payment dates before the invoice's issue date are refused.

## Decisions

Questions that aren't a simple switch. For each: the two ways to read it, and what this version does.

### In a group lesson, is "pupil absent" recorded per pupil or for the whole occurrence?

- One reading: Status is on the occurrence, so marking absent affects every pupil in the group
- The other: Absence is per pupil on that date, while "cancelled by school" applies to the whole occurrence
- **This version: Absence is per pupil on that date, while "cancelled by school" applies to the whole occurrence.**

### How does one pupil leave or join a group slot mid-term while others stay?

- One reading: Pupils can only be added or removed for the slot's whole range; to change mid-term the slot must be ended and a new one created
- The other: Each pupil on a slot has their own start and end date
- **This version: Pupils can only be added or removed for the slot's whole range; to change mid-term the slot must be ended and a new one created.**

### What is the "remaining invoice total" a credit note may not exceed?

- One reading: Total minus earlier credit notes
- The other: Total minus earlier credit notes (payments are handled by refunds afterwards)
- **This version: Total minus earlier credit notes (payments are handled by refunds afterwards).**

### How are failed logins counted for lockout?

- One reading: Any 5 failures ever, never reset
- The other: 5 consecutive failures, reset on a successful login or when a lock expires; the reset by an admin also clears it
- **This version: 5 consecutive failures, reset on a successful login or when a lock expires; the reset by an admin also clears it.**
