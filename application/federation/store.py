"""Per-node federation store (`federation.sqlite`): inbox, rejections, adoption records, outbox chain. It is NOT the ledger: it is outside H1/H2 and the checkpoint, so a local
attacker can edit it. Nothing read from it can change a ledger (adoption re-verifies the stored signed envelope), and nothing here is ever written into a ledger.
"""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox(alert_hash TEXT PRIMARY KEY, alert_id TEXT UNIQUE NOT NULL, issuer TEXT NOT NULL, seq INTEGER NOT NULL, envelope TEXT NOT NULL, received_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS hwm(issuer TEXT PRIMARY KEY, seq INTEGER NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rejections(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, reason TEXT NOT NULL, detail TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS adoptions(alert_id TEXT PRIMARY KEY, operator TEXT NOT NULL, at INTEGER NOT NULL, local_lot TEXT NOT NULL, slots TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox(seq INTEGER PRIMARY KEY, response_id TEXT NOT NULL, alert_id TEXT NOT NULL, hash TEXT NOT NULL, path TEXT NOT NULL);
"""


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def hwm(self, issuer):
        row = self.db.execute("SELECT seq,hash FROM hwm WHERE issuer=?", (issuer,)).fetchone()
        return (row["seq"], row["hash"]) if row else (0, None)

    def accept(self, alert_hash, body, envelope, now):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?)", (alert_hash, body["alertId"], body["issuer"], body["seq"], json.dumps(envelope), now))
            self.db.execute("INSERT INTO hwm VALUES(?,?,?) ON CONFLICT(issuer) DO UPDATE SET seq=excluded.seq,hash=excluded.hash", (body["issuer"], body["seq"], alert_hash))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def reject(self, reason, detail, sha256, now=None):
        self.db.execute("INSERT INTO rejections(at,reason,detail,sha256) VALUES(?,?,?,?)", (int(time.time()) if now is None else now, reason, detail, sha256))

    def alert(self, alert_id):
        row = self.db.execute("SELECT alert_hash,envelope FROM inbox WHERE alert_id=?", (alert_id,)).fetchone()
        return (row["alert_hash"], json.loads(row["envelope"])) if row else (None, None)

    def adoption(self, alert_id):
        return self.db.execute("SELECT * FROM adoptions WHERE alert_id=?", (alert_id,)).fetchone()

    def record_adoption(self, alert_id, operator, now, local_lot, slots, outcome, detail=""):
        self.db.execute("INSERT OR REPLACE INTO adoptions VALUES(?,?,?,?,?,?,?)", (alert_id, operator, now, local_lot, json.dumps(slots), outcome, detail))

    def last_response(self):
        row = self.db.execute("SELECT seq,hash FROM outbox ORDER BY seq DESC LIMIT 1").fetchone()
        return (row["seq"], row["hash"]) if row else (0, None)

    def add_response(self, seq, response_id, alert_id, digest, path):
        self.db.execute("INSERT INTO outbox VALUES(?,?,?,?,?)", (seq, response_id, alert_id, digest, str(path)))

    def rejections(self):
        return [dict(r) for r in self.db.execute("SELECT at,reason,detail,sha256 FROM rejections ORDER BY id")]
