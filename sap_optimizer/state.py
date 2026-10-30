"""Local metadata only; never store prompts, tool arguments, source, or credentials."""
import json
import os
import sqlite3
import time
from pathlib import Path


class State:
    def __init__(self, root):
        root = Path(root).resolve()
        directory = root / ".sap-context"
        if directory.is_symlink():
            raise OSError("State directory must not be a symbolic link")
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        self.path = directory / "state.sqlite3"
        if self.path.is_symlink():
            raise OSError("State database must not be a symbolic link")
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS metrics (at REAL, kind TEXT, data TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS turns (session TEXT PRIMARY KEY, sap INTEGER, body INTEGER, warned INTEGER)")
        os.chmod(self.path, 0o600)

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def metric(self, kind, **data):
        # Callers supply aggregate numbers or fixed labels only.
        with self.connect() as db:
            db.execute("INSERT INTO metrics VALUES (?,?,?)", (time.time(), kind, json.dumps(data)))

    def begin(self, session, sap):
        with self.connect() as db:
            previous = db.execute("SELECT sap FROM turns WHERE session=?", (session,)).fetchone()
            sap = bool(sap or (previous and previous[0]))
            db.execute("INSERT OR REPLACE INTO turns VALUES (?,?,0,0)", (session, int(sap)))
        return sap

    def mark_body(self, session):
        with self.connect() as db:
            db.execute("UPDATE turns SET body=1 WHERE session=?", (session,))

    def turn(self, session):
        with self.connect() as db:
            row = db.execute("SELECT sap,body,warned FROM turns WHERE session=?", (session,)).fetchone()
        return row or (0, 0, 0)

    def warn(self, session):
        with self.connect() as db:
            db.execute("UPDATE turns SET warned=1 WHERE session=?", (session,))

    def summary(self):
        with self.connect() as db:
            rows = db.execute("SELECT kind,data FROM metrics").fetchall()
        counts, numeric = {}, {}
        for kind, raw in rows:
            counts[kind] = counts.get(kind, 0) + 1
            for key, val in json.loads(raw).items():
                if type(val) in (int, float):
                    numeric[key] = numeric.get(key, 0) + val
        return {"events": counts, "totals": numeric,
                "token_counts": "not measured by gateway; import Claude result usage separately",
                "cost_usd": None}
