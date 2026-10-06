#!/bin/sh
# Lesson Ledger: install check and start. Usage:
#   ./run.sh                 start the service (default)
#   ./run.sh demo            load demo data (empty database only)
#   ./run.sh backup [FILE]   write a backup
#   ./run.sh restore FILE    restore a backup (stop the service first)
#   ./run.sh test            run the automated test suite
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.9 or newer is required. Install it (e.g. 'sudo apt install python3') and run this again." >&2
  exit 1
fi
"$PY" -c 'import sys, sqlite3, zoneinfo; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "Python 3.9 or newer (with sqlite3) is required." >&2; exit 1; }
if [ "$1" = "test" ]; then
  exec "$PY" -m unittest -v tests.test_core tests.test_web
fi
[ $# -eq 0 ] && set -- serve
exec "$PY" -m lessonledger "$@"
