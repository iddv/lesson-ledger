"""Command line: serve | demo | backup [FILE] | restore FILE | check-backup FILE"""
import logging
import os
import sys

from . import core, db


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else 'serve'
    cfg = db.load_config()
    logging.basicConfig(level=getattr(logging, cfg['log_level'].upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        if cmd == 'serve':
            from . import web
            web.serve(cfg)
        elif cmd == 'demo':
            from . import demo
            c = db.open_db(cfg)
            with db.tx(c):
                creds = demo.load(c)
            print('Demo data loaded. Sign in with:')
            for u, p in creds:
                print(f'  username: {u:6}  password: {p}')
            print('You will be asked to change the password at first sign-in.')
        elif cmd == 'backup':
            c = db.open_db(cfg)
            path = argv[1] if len(argv) > 1 else None
            path = db.backup_to(c, path) if path else db.write_backup(c, cfg, prefix='manual')
            print(f'Backup written: {path}')
        elif cmd == 'check-backup':
            print(f'OK: schema version {db.check_backup(argv[1])}')
        elif cmd == 'restore':
            if len(argv) < 2:
                raise SystemExit('Usage: restore FILE')
            kept = db.restore(cfg, argv[1])
            print('Restore complete.' + (f' The previous data was kept in {kept}.' if kept else ''))
            print('Start the service again to use the restored data.')
        else:
            print(__doc__)
            return 2
    except (db.BackupError, core.Invalid) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
