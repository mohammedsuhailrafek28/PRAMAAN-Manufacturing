"""Append-only staging store: original source bytes and rows, every transformation step, canonical events and every disposition ever decided.

A separate SQLite file from the ledger. It never holds anything the ledger relies on; its job is provenance and repeatability. Rows are never updated
or deleted (triggers enforce it), so what a source said, how it was transformed and what was decided stay reconstructable.
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import FileResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_files(sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, source_system TEXT NOT NULL, mapping_id TEXT NOT NULL,
  mapping_sha256 TEXT NOT NULL, format TEXT NOT NULL, bytes INTEGER NOT NULL, content BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS source_records(file_sha256 TEXT NOT NULL, row_index INTEGER NOT NULL, raw_json TEXT NOT NULL, PRIMARY KEY(file_sha256,row_index));
CREATE TABLE IF NOT EXISTS transformations(file_sha256 TEXT NOT NULL, row_index INTEGER NOT NULL, seq INTEGER NOT NULL, field TEXT NOT NULL, step TEXT NOT NULL,
  before TEXT, after TEXT, PRIMARY KEY(file_sha256,row_index,seq));
CREATE TABLE IF NOT EXISTS canonical_events(canonical_id TEXT NOT NULL, content_sha256 TEXT NOT NULL, source_system TEXT NOT NULL, source_record_id TEXT NOT NULL,
  kind TEXT NOT NULL, motor TEXT, occurred_at TEXT NOT NULL, canonical_json TEXT NOT NULL, file_sha256 TEXT NOT NULL, row_index INTEGER NOT NULL,
  PRIMARY KEY(canonical_id,content_sha256));
CREATE TABLE IF NOT EXISTS runs(run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, mode TEXT NOT NULL, files_json TEXT NOT NULL,
  options_json TEXT NOT NULL, tools_json TEXT NOT NULL, ledger_head_before TEXT);
CREATE TABLE IF NOT EXISTS run_results(run_id INTEGER PRIMARY KEY, finished_at TEXT NOT NULL, status TEXT NOT NULL, ledger_head_after TEXT, report_sha256 TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS dispositions(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, file_sha256 TEXT NOT NULL, row_index INTEGER NOT NULL,
  canonical_id TEXT, content_sha256 TEXT, outcome TEXT NOT NULL, disposition TEXT NOT NULL, reason TEXT, issues_json TEXT NOT NULL, ledger_event_ids_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dispositions_canonical ON dispositions(canonical_id, id);
"""
IMMUTABLE = ("source_files", "source_records", "transformations", "canonical_events", "runs", "run_results", "dispositions")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tool_versions():
    import frictionless, pandas, pydantic
    return dict(python=sys.version.split()[0], pandas=pandas.__version__, pydantic=pydantic.__version__, frictionless=frictionless.__version__)


def _j(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


class Staging:
    def __init__(self, path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for t in IMMUTABLE:
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_no_{action.lower()} BEFORE {action} ON {t} BEGIN SELECT RAISE(ABORT,'staging is append-only'); END")
        self.db.commit()

    def close(self):
        self.db.close()

    def latest(self, canonical_id):
        """Most recent disposition decided for a canonical id -> Row or None."""
        return self.db.execute("SELECT * FROM dispositions WHERE canonical_id=? ORDER BY id DESC LIMIT 1", (canonical_id,)).fetchone()

    def latest_accepted(self, canonical_id):
        return self.db.execute("SELECT * FROM dispositions WHERE canonical_id=? AND outcome='ACCEPTED' ORDER BY id DESC LIMIT 1", (canonical_id,)).fetchone()

    def accepted_quality(self, motor):
        """Quality inspections previously accepted for a motor -> [canonical dict]."""
        rows = self.db.execute("""SELECT c.canonical_json FROM canonical_events c JOIN dispositions d ON d.canonical_id=c.canonical_id AND d.content_sha256=c.content_sha256
                                  WHERE c.kind='QUALITY_INSPECTION' AND c.motor=? AND d.outcome='ACCEPTED' GROUP BY c.canonical_id, c.content_sha256""", (motor,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def begin_run(self, mode, files, options, ledger_head):
        with self.db:
            cur = self.db.execute("INSERT INTO runs(started_at,mode,files_json,options_json,tools_json,ledger_head_before) VALUES(?,?,?,?,?,?)",
                                  (now(), mode, _j(files), _j(options), _j(tool_versions()), ledger_head))
        return cur.lastrowid

    def end_run(self, run_id, status, ledger_head, report_sha, detail=None):
        with self.db:
            self.db.execute("INSERT INTO run_results VALUES(?,?,?,?,?,?)", (run_id, now(), status, ledger_head, report_sha, detail))

    def preserve(self, files: list[FileResult]):
        """Write originals, rows, transformation steps and canonical events. Idempotent: the same bytes/rows are never stored twice."""
        with self.db:
            for f in files:
                self.db.execute("INSERT OR IGNORE INTO source_files VALUES(?,?,?,?,?,?,?,?)",
                                (f.sha256, f.name, f.sourceSystem, f.mappingId, f.mappingSha256, f.format, f.bytes, f.content))
                for r in f.records:
                    self.db.execute("INSERT OR IGNORE INTO source_records VALUES(?,?,?)", (f.sha256, r.rowIndex, _j(r.raw)))
                    for seq, s in enumerate(r.steps):
                        self.db.execute("INSERT OR IGNORE INTO transformations VALUES(?,?,?,?,?,?,?)",
                                        (f.sha256, r.rowIndex, seq, s.field, s.step, _j(s.before), _j(s.after)))
                    if r.canonical is not None:
                        c = r.canonical
                        self.db.execute("INSERT OR IGNORE INTO canonical_events VALUES(?,?,?,?,?,?,?,?,?,?)",
                                        (c.canonicalId, c.contentSha256, c.sourceSystem.value, c.sourceRecordId, c.kind.value, c.motorSerial, c.occurredAt,
                                         c.model_dump_json(), f.sha256, r.rowIndex))

    def record_dispositions(self, run_id, files: list[FileResult]):
        with self.db:
            for f in files:
                for r in f.records:
                    c = r.canonical
                    self.db.execute("INSERT INTO dispositions(run_id,file_sha256,row_index,canonical_id,content_sha256,outcome,disposition,reason,issues_json,ledger_event_ids_json) "
                                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                                    (run_id, f.sha256, r.rowIndex, c.canonicalId if c else None, c.contentSha256 if c else None, r.outcome or "REJECTED",
                                     r.disposition or "UNDECIDED", r.reason, _j([i.model_dump() for i in r.issues]), _j(r.ledgerEventIds)))
