import json
import sqlite3
import time
from contextlib import contextmanager


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS observations (
                    name TEXT PRIMARY KEY, observed REAL NOT NULL, metrics TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, time REAL, actor TEXT, action TEXT,
                    target TEXT, result TEXT
                );
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def observe(self, name, metrics):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO observations VALUES (?, ?, ?)',
                       (name, time.time(), json.dumps(metrics)))

    def observations(self):
        with self.connect() as db:
            return {n: {'observed_at': t, **json.loads(m)} for n, t, m in db.execute('SELECT * FROM observations')}

    def audit(self, actor, action, target, result):
        with self.connect() as db:
            db.execute('INSERT INTO audit(time,actor,action,target,result) VALUES(?,?,?,?,?)',
                       (time.time(), actor, action, target, result))
            db.execute('DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM audit)')

    def events(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
