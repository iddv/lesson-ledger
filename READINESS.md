# Readiness

Where Lesson Ledger stands on the way to production: each item was checked by doing it (installing from the README, starting it, backing it up and restoring it, ...) or by reading the repository. Green is ready, amber needs attention before production, red is a gap.

**8 green, 12 amber, 0 red**.

| item | status | why | next step to production |
|---|---|---|---|
| Clean install from the README | amber | not checked | check it by hand before production |
| The README's quick-start commands work as written (install, run, backup) | green | 2 quick-start command(s) worked as written on a fresh copy; 1 not run (has a placeholder to fill in) | - |
| Listens on localhost unless configured | amber | not checked | check it by hand before production |
| Starts empty; demo data only on an explicit flag or command | amber | not checked | check it by hand before production |
| First-run admin setup, no default password | amber | not checked | check it by hand before production |
| Configuration by environment or file, every option documented | amber | not checked | check it by hand before production |
| Data location documented | amber | not checked | check it by hand before production |
| Backup and restore work end to end | amber | not checked | check it by hand before production |
| Data survives a restart | amber | not checked | check it by hand before production |
| Starts again at once after a stop or a crash (services) | green | `./run.sh` on 127.0.0.1:8080 served again 0.11 s after a graceful stop and 0.11 s after a SIGKILL | - |
| Graceful shutdown | amber | not checked | check it by hand before production |
| Health endpoint (services) | amber | not checked | check it by hand before production |
| Readable logs, no secrets or personal data | amber | not checked | check it by hand before production |
| Schema changes and upgrades keep the data | amber | not checked | check it by hand before production |
| CI workflow installs the project and runs the tests | green | .github/workflows/test.yml installs and runs the tests | - |
| Dependencies locked or pinned | green | no third-party runtime dependencies (standard library only) | - |
| Sensible .gitignore, no build artefacts in the repository | green | .gitignore covers caches and environments | - |
| README covers install, configure, run, upgrade, backup and restore, troubleshooting and limitations | green | every section is there | - |
| The documented test commands run green, as written | green | 34 own test(s) pass; the acceptance suite is green (83 pass, 1 known open item(s) marked); the README's test commands run green as written | - |
| User-facing docs in plain words | green | no build-process jargon in README, ASSUMPTIONS, SECURITY, READINESS or the tests | - |

## Security

See `SECURITY.md`: 6 finding(s), 3 not fixed by a tested change (low 3).

## Known open items in the tests

Marked as expected failures in `tests/acceptance/` (the suite stays green):

- `test_database_backups_readable_only_account_runs_service.py`: Known security issue (low): The database and backups are readable only by the account that runs the service
