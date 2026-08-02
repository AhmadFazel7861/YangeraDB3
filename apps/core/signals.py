"""
Core signals — SQLite optimizations and startup tasks.
"""
from django.db.backends.signals import connection_created


def optimize_sqlite(sender, connection, **kwargs):
    """Apply SQLite performance optimizations on every connection."""
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA synchronous=NORMAL;')
        cursor.execute('PRAGMA cache_size=10000;')
        cursor.execute('PRAGMA foreign_keys=ON;')
        cursor.execute('PRAGMA temp_store=MEMORY;')


connection_created.connect(optimize_sqlite)