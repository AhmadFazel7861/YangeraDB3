"""
run.py — Production launcher using Waitress WSGI server
قنادی تیموریان — ERP System
Designed by YangEra
"""

import sys
import os
import threading
import webbrowser
import time

# ─── Path setup ───────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

sys.path.insert(0, BUNDLE_DIR)
sys.path.insert(0, BASE_DIR)

# ─── Django settings ──────────────────────────────────────────────────────────
os.environ['DJANGO_SETTINGS_MODULE'] = 'erp_project.settings'

# ─── Paths ────────────────────────────────────────────────────────────────────
db_dir = os.path.join(BASE_DIR, 'db')
os.makedirs(db_dir, exist_ok=True)
os.environ['DB_PATH'] = os.path.join(db_dir, 'erp_taimourian.sqlite3')
os.environ['STATIC_ROOT_OVERRIDE'] = os.path.join(BUNDLE_DIR, 'staticfiles')
os.environ['MEDIA_ROOT_OVERRIDE']  = os.path.join(BASE_DIR, 'media')

HOST = '127.0.0.1'
PORT = 8765


def open_browser():
    time.sleep(2)
    webbrowser.open(f'http://{HOST}:{PORT}/')


def run_migrations():
    from django.core.management import call_command
    try:
        call_command('migrate', '--run-syncdb', verbosity=0)
    except Exception as e:
        print(f'[Migration] {e}')


def main():
    print('=' * 50)
    print('  قنادی تیموریان')
    print(f'  Starting at http://{HOST}:{PORT}/')
    print('=' * 50)

    import django
    django.setup()
    run_migrations()

    # Open browser after short delay
    threading.Thread(target=open_browser, daemon=True).start()

    # Use Waitress — fast production WSGI server
    try:
        from waitress import serve
        from erp_project.wsgi import application
        print(f'\n✓ Server ready at http://{HOST}:{PORT}/')
        print('  Close this window to stop.\n')
        serve(
            application,
            host=HOST,
            port=PORT,
            threads=4,
            channel_timeout=120,
            cleanup_interval=30,
        )
    except ImportError:
        # Fallback to Django dev server if waitress not available
        print('  [Waitress not found, using Django server]')
        from django.core.management import call_command
        call_command('runserver', f'{HOST}:{PORT}', '--noreload', '--nothreading')


if __name__ == '__main__':
    main()