"""Adversarial tests for the hybrid proof: the full image proof on every query, the evidence-content generation only to decide a mismatch.
Run: python -B -m unittest performance.test_hybrid_proof -v

Safety intent: a projection is only ever served while the complete image proof, or (on mismatch) the complete digest of EVERY byte it can read, still equals the
verified one; any change inside that scope fails closed until an explicit rebuild; bytes outside the scope (header counters, clock, audit, decision runs,
announcements, tickets) are re-anchored, never rebuilt, never able to excuse an evidence change.
"""
import hashlib
import json
import os
import random
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from application.service import Manufacturing
from performance import evidence_scope as scope
from performance import impact_query
from performance.impact_query import ImpactQuery, ImpactUnavailable, ReadOnlyLedger, verify_motor
from pramaan_integration import Ledger, ValidationFailure

LOTS = ("BR-204", "BR-310", "BR-312", "BR-2O4", "NSB-204", "BR-999")
MOTORS = ("MTR-GEN-001", "MTR-GEN-002", "MTR-GEN-003", "MTR-GEN-004")


def build(path, de001="BR-204"):
    app = Manufacturing(path)
    for m in MOTORS:
        app.create_unit(m)
    for m, de in zip(MOTORS[:3], (de001, "BR-310", "BR-310")):
        app.assemble(m, de, "BR-312"); app.record_historical_shipment_fixture(m)
    app.observe("MTR-GEN-003", "BR-2O4")
    return app


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pramaan-gen-test-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.path = self.dir / "ledger.sqlite"
        self.app = build(self.path)
        self.addCleanup(self.app.close)
        self.reader = ImpactQuery(self.path)
        self.addCleanup(self.reader.close)
        self.reader.rebuild()

    def answers(self, reader=None):
        reader = reader or self.reader
        return {lot: reader.query(lot) for lot in LOTS}

    def raw(self):
        """A plain connection for tampering (foreign keys off, as in an attacker's editor)."""
        con = sqlite3.connect(str(self.path), isolation_level=None)
        self.addCleanup(con.close)
        return con

    def drop_guards(self, con):
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%no_%'").fetchall():
            con.execute(f'DROP TRIGGER "{name}"')

    def assertStale(self):
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED_REBUILD_REQUIRED"):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
            self.reader.query("BR-204")


class DigestUnit(unittest.TestCase):
    BASE = [1, "id", "MTR", "SRC", 1, "native", "epcis", "cap", "prev", "hash"]       # an events row; native/epcis are the large (typed, length-prefixed) columns

    def digest(self, **changes):
        import hashlib as h
        row = list(self.BASE)
        for index, value in changes.items():
            row[int(index[1:])] = value
        x = h.sha256()
        scope.feed(x, tuple(row), scope.SPLITS["events"])
        return x.hexdigest()

    def test_field_boundaries_and_types_are_unambiguous(self):
        pairs = [(dict(c5="ab", c6="c"), dict(c5="a", c6="bc")),                 # boundary between the two large fields
                 (dict(c5="", c6=None), dict(c5=None, c6="")),                   # empty versus NULL, in both large fields
                 (dict(c5=None, c6="x"), dict(c5="x", c6=None)),                 # position of a lone large field
                 (dict(c1="a', 'b", c2="c"), dict(c1="a", c2="b', 'c")),         # quote games inside short fields
                 (dict(c0=1), dict(c0="1")), (dict(c4=1), dict(c4=None)), (dict(c1=b"x"), dict(c1="x")),
                 (dict(c5=b"x"), dict(c5="x")),                                  # BLOB versus TEXT in a large column
                 (dict(c0=0), dict(c0=None)), (dict(c0=-1), dict(c0=1))]
        for a, b in pairs:
            self.assertNotEqual(self.digest(**a), self.digest(**b), (a, b))
        self.assertEqual(self.digest(), self.digest())

    def test_wrong_row_width_fails_closed(self):
        import hashlib as h
        with self.assertRaises(ValueError):
            scope.feed(h.sha256(), tuple(self.BASE[:9]), scope.SPLITS["events"])

    def test_scope_is_the_declared_tables_only(self):
        self.assertEqual(set(scope.SCOPE), {"motors", "events", "captures", "rejections", "app_units"})
        for forbidden in ("app_clock", "app_audit", "app_audit_head", "decision_runs", "recall_announcements", "app_ship_tickets"):
            self.assertNotIn(forbidden, scope.SCOPE)

    def test_motor_digest_is_bound_to_the_serial(self):
        con = sqlite3.connect(":memory:")
        con.executescript("CREATE TABLE motors(serial TEXT, config TEXT, hash TEXT); CREATE TABLE captures(hash TEXT, raw BLOB, received TEXT);"
                          "CREATE TABLE events(ordinal INTEGER PRIMARY KEY, id TEXT, motor TEXT, source TEXT, seq INT, native TEXT, epcis TEXT, capture TEXT, previous TEXT, hash TEXT);"
                          "CREATE TABLE rejections(ordinal INTEGER PRIMARY KEY, motor TEXT, raw_hash TEXT, reason TEXT, received TEXT);"
                          "INSERT INTO motors VALUES('A','c','h'),('B','c','h');")
        self.assertNotEqual(scope.motor_digest(con, "A")[0], scope.motor_digest(con, "B")[0])
        self.assertNotEqual(scope.motor_digest(con, "A")[0], scope.motor_digest(con, "C")[0])


class ScopeCompleteness(Base):
    def test_reader_reads_only_declared_columns(self):
        reads = set()

        def authorizer(action, a1, a2, db, src):
            if action == sqlite3.SQLITE_READ:
                reads.add((a1, a2))
            return sqlite3.SQLITE_OK
        self.reader.db.set_authorizer(authorizer)
        try:
            self.reader.rebuild(); self.reader.query("BR-204"); self.reader.query_json("BR-310")
        finally:
            self.reader.db.set_authorizer(None)
        self.assertTrue(reads)
        for table, column in reads:
            if table in ("sqlite_master", "sqlite_schema"):
                continue
            self.assertIn(table, scope.SCOPE, (table, column))
            self.assertTrue(column == "" or column in scope.SCOPE[table], (table, column))

    def test_every_scope_column_changes_the_generation_and_restores_it(self):
        con = self.raw()
        con.execute("INSERT INTO rejections(motor,raw_hash,reason,received) VALUES('MTR-GEN-004','x','y','z')")        # populate every table
        self.drop_guards(con)
        base = scope.fleet_state(con, "REG").fleet
        self.assertEqual(scope.fleet_state(con, "REG").fleet, base)                                                      # deterministic
        self.assertNotEqual(scope.fleet_state(con, "OTHER-REG").fleet, base)                                             # the registry is part of the generation
        for table, columns in scope.SCOPE.items():
            for column in columns:
                row = con.execute(f"SELECT rowid, {column} FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
                self.assertIsNotNone(row, table)
                con.execute(f"UPDATE {table} SET {column} = CASE typeof({column}) WHEN 'integer' THEN {column}+1000000 WHEN 'blob' THEN {column}||x'00' ELSE {column}||'x' END WHERE rowid=?", (row[0],))
                changed = scope.fleet_state(con, "REG").fleet
                moved = row[0] + 1000000 if column == "ordinal" else row[0]                                     # an INTEGER PRIMARY KEY column is the rowid
                con.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", (row[1], moved))
                self.assertNotEqual(changed, base, f"{table}.{column} is outside the digest")
                self.assertEqual(scope.fleet_state(con, "REG").fleet, base, f"{table}.{column} did not restore")

    def test_streaming_fleet_digests_equal_the_per_motor_digests_workers_use(self):
        con = self.raw()
        con.execute("INSERT INTO rejections(motor,raw_hash,reason,received) VALUES('MTR-GEN-004','x','y','z')")
        state = scope.fleet_state(con, "REG")
        self.assertEqual(set(state.motors), set(MOTORS))
        for serial, digest in state.motors.items():
            self.assertEqual(scope.motor_digest(con, serial)[0], digest, serial)
        self.assertEqual(scope.motor_digest(con, "MTR-NOBODY")[0], scope.motor_digest(con, "MTR-NOBODY")[0])

    def test_schema_guard_removal_changes_the_generation(self):
        con = self.raw()
        con.execute("DROP TRIGGER events_no_delete")
        self.assertStale()

    def test_unreferenced_capture_and_foreign_rows_change_the_generation(self):
        con = self.raw()
        con.execute("INSERT INTO captures VALUES('f'||hex(randomblob(8)), x'00', 'now')")
        self.assertStale()
        self.reader.rebuild()
        self.drop_guards(con)
        con.execute("INSERT INTO events(id,motor,source,seq,native,epcis,capture,previous,hash) VALUES('urn:x','MTR-NOBODY','S',1,'{}','{}','c','p','h')")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")


class HarmlessWritesAreReanchoredNotRebuilt(Base):
    """Bytes the projection cannot read change the image proof but not the evidence generation: the verified projection is reused, nothing is re-verified."""
    def assertReanchored(self, before, label, expected_total):
        with patch.object(impact_query, "verify_motor", side_effect=AssertionError("no verification expected")), \
             patch.object(Ledger, "_verified_rows", side_effect=AssertionError("no decode expected")):
            after = self.answers()
        strip = lambda answers: {lot: {k: v for k, v in r.items() if k != "contentDigest"} for lot, r in answers.items()}
        self.assertEqual(strip(after), strip(before), label)
        if expected_total is not None:
            self.assertEqual(self.reader.stats["reAnchors"], expected_total, label)
        self.assertEqual(self.reader.generation, before["BR-204"]["evidenceGeneration"], label)

    def test_open_close_and_clock_ticks(self):
        before = self.answers()
        for _ in range(3):
            Manufacturing(self.path).close()
        self.assertReanchored(before, "open/close", 1)                                                         # one re-anchor serves all six queries
        before = self.answers()
        self.app.tick(); self.app.tick()
        self.assertReanchored(before, "clock", 2)

    def test_audit_decision_announcement_and_ticket_writes(self):
        before = self.answers()
        self.app.announce("BR-204", ["DE"])                                      # recall announcement, audit append, decision runs
        self.assertReanchored(before, "announce", 1)
        before = self.answers()
        con = self.raw()
        con.execute("INSERT INTO app_ship_tickets VALUES('MTR-GEN-001','fp')")
        con.execute("INSERT INTO decision_runs(motor,policy_hash,payload,hash) VALUES('MTR-GEN-001','p','{}','h')")
        con.execute("PRAGMA user_version=77")
        self.assertReanchored(before, "tickets and decision rows", 2)

    def test_checkpoint_truncate_and_vacuum(self):
        before = self.answers()
        con = self.raw()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.app.db.commit()
        con.execute("VACUUM")
        self.assertReanchored(before, "vacuum and checkpoint (page layout and free pages are not evidence)", None)

    def test_refused_command_writes_nothing(self):
        before = self.answers()
        with self.assertRaises(ValidationFailure):
            self.app.create_unit(MOTORS[0])                                      # duplicate serial: refused, nothing written
        self.assertEqual(self.answers(), before)                                 # not even an image-proof difference
        self.assertEqual(self.reader.stats["reAnchors"], 0)

    def test_harmless_writes_do_not_make_a_rebuild_reverify_anything(self):
        Manufacturing(self.path).close(); self.app.tick(); self.app.announce("BR-204", ["DE"])
        with patch.object(Ledger, "_verified_rows", side_effect=AssertionError("no verification expected")):
            info = self.reader.rebuild()
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (0, 4))

    def test_after_a_reanchor_the_next_query_matches_the_image_proof_again(self):
        Manufacturing(self.path).close()
        self.reader.query("BR-204")
        matches = self.reader.stats["imageProofMatches"]
        self.reader.query("BR-204")
        self.assertEqual((self.reader.stats["imageProofMatches"], self.reader.stats["reAnchors"]), (matches + 1, 1))

    def test_serialized_payload_after_a_reanchor_carries_the_current_image_proof(self):
        first = self.reader.query_json("BR-204")
        Manufacturing(self.path).close()
        second = self.reader.query_json("BR-204")
        self.assertNotEqual(first, second)
        self.assertEqual(json.loads(second)["contentDigest"], self.reader._key)
        self.assertEqual(json.loads(second)["evidenceGeneration"], json.loads(first)["evidenceGeneration"])
        self.assertIs(self.reader.query_json("BR-204"), second)

    def test_a_harmless_write_never_excuses_a_simultaneous_evidence_change(self):
        self.app.tick()
        self.app.observe("MTR-GEN-004", "BR-204")                                # both kinds of change before the next query
        self.assertStale()

    def test_hybrid_never_computes_the_generation_on_the_normal_path(self):
        with patch.object(scope, "fleet_state", side_effect=AssertionError("generation must not be computed when the image proof matches")):
            for lot in LOTS:
                self.reader.query(lot); self.reader.query_json(lot)

    def test_every_query_recomputes_the_full_image_proof(self):
        calls = []
        original = self.reader._content_key
        with patch.object(self.reader, "_content_key", side_effect=lambda r: (calls.append(1), original(r))[1]):
            for lot in LOTS:
                self.reader.query(lot); self.reader.query_json(lot)
        self.assertEqual(len(calls), 2 * len(LOTS))
        self.assertGreater(self.reader._image_bytes, 0)


class EvidenceChangesAreDetected(Base):
    def test_modified_in_every_verified_events_column(self):
        for column in ("native", "epcis", "source", "seq", "previous", "hash", "capture", "id", "motor"):
            with self.subTest(column=column):
                self.setUp() if column != "native" else None
                con = self.raw(); self.drop_guards(con)
                row = con.execute(f"SELECT rowid, {column} FROM events WHERE motor='MTR-GEN-001' ORDER BY ordinal LIMIT 1").fetchone()
                con.execute(f"UPDATE events SET {column} = CASE typeof({column}) WHEN 'integer' THEN {column}+7 ELSE {column}||'x' END WHERE rowid=?", (row[0],))
                with self.assertRaises(ImpactUnavailable):
                    self.reader.query("BR-204")
                with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
                    self.reader.rebuild()
                with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
                    self.reader.query("BR-204")

    def test_received_timestamp_is_evidence_for_the_generation_even_though_verification_ignores_it(self):
        con = self.raw(); self.drop_guards(con)
        con.execute("UPDATE captures SET received='2000-01-01T00:00:00Z' WHERE hash=(SELECT capture FROM events WHERE motor='MTR-GEN-001' LIMIT 1)")
        self.assertStale()

    def test_deleted_tail_middle_and_whole_motor(self):
        events = [r[0] for r in self.raw().execute("SELECT ordinal FROM events WHERE motor='MTR-GEN-001' ORDER BY ordinal")]
        self.assertGreater(len(events), 2)
        con = self.raw(); self.drop_guards(con)
        con.execute("DELETE FROM events WHERE ordinal=?", (events[-1],))                                      # tail: chain still valid
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "ROLLBACK_OR_CONFIGURATION_REWRITE"):                  # hashes accepted earlier are gone
            self.reader.rebuild()
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
            self.reader.query("BR-204")
        fresh = ImpactQuery(self.path)                                                                         # a restarted reader has no earlier acceptance to compare with
        self.addCleanup(fresh.close)
        fresh.rebuild()                                                                                        # (documented limitation: no external anchor)
        con.execute("DELETE FROM events WHERE ordinal=?", (events[1],))                                        # middle: chain broken
        with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
            fresh.rebuild()

    def test_reordered_events(self):
        rows = self.raw().execute("SELECT ordinal FROM events WHERE motor='MTR-GEN-001' ORDER BY ordinal LIMIT 2").fetchall()
        a, b = rows[0][0], rows[1][0]
        con = self.raw(); self.drop_guards(con)
        con.execute("UPDATE events SET ordinal=-1 WHERE ordinal=?", (a,))
        con.execute("UPDATE events SET ordinal=? WHERE ordinal=?", (a, b))
        con.execute("UPDATE events SET ordinal=? WHERE ordinal=-1", (b,))
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
            self.reader.rebuild()

    def test_substituted_capture_bytes_and_swapped_motor_rows(self):
        con = self.raw(); self.drop_guards(con)
        h1, h2 = [r[0] for r in con.execute("SELECT capture FROM events WHERE motor IN ('MTR-GEN-001','MTR-GEN-002') GROUP BY motor ORDER BY motor")]
        raw2 = con.execute("SELECT raw FROM captures WHERE hash=?", (h2,)).fetchone()[0]
        con.execute("UPDATE captures SET raw=? WHERE hash=?", (raw2, h1))                                      # another valid document under this hash
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
            self.reader.rebuild()
        con.execute("UPDATE captures SET raw=(SELECT raw FROM captures WHERE hash=?) WHERE hash=?", (h1, h1))
        self.setUp()
        con = self.raw(); self.drop_guards(con)
        con.execute("UPDATE events SET motor='MTR-GEN-002' WHERE motor='MTR-GEN-001'")                         # event rows moved to another motor
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
            self.reader.rebuild()

    def test_configuration_row_rewrite_is_detected(self):
        before = self.answers()
        con = self.raw(); self.drop_guards(con)
        con.execute("UPDATE motors SET config=config||' ' WHERE serial='MTR-GEN-002'")                        # same parsed configuration, different stored bytes
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED"):                                    # any stored byte counts as a change
            self.reader.query("BR-204")
        self.reader.rebuild()                                                                                  # verification is semantic and passes: identical answers
        self.assertEqual({k: {m: v for m, v in r.items() if m not in ("contentDigest", "evidenceGeneration")} for k, r in self.answers().items()},
                         {k: {m: v for m, v in r.items() if m not in ("contentDigest", "evidenceGeneration")} for k, r in before.items()})
        config = json.loads(con.execute("SELECT config FROM motors WHERE serial='MTR-GEN-002'").fetchone()[0])
        config["coverage"]["coveragePolicyId"] = "REWRITTEN"                                                   # a semantic rewrite with a recomputed hash is refused
        from pramaan_integration.profile import digest
        con.execute("UPDATE motors SET config=?, hash=? WHERE serial='MTR-GEN-002'", (json.dumps(config), digest(config)))
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "ROLLBACK_OR_CONFIGURATION_REWRITE"):
            self.reader.rebuild()

    def test_rejection_row_blocks_the_motor(self):
        con = self.raw()
        con.execute("INSERT INTO rejections(motor,raw_hash,reason,received) VALUES('MTR-GEN-002','h','r','t')")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "INPUT_VERIFICATION_FAILED"):
            self.reader.rebuild()

    def test_older_database_restored_under_a_running_reader(self):
        old = self.dir / "old.sqlite"
        src = sqlite3.connect(str(self.path)); dst = sqlite3.connect(str(old)); src.backup(dst); dst.close(); src.close()
        self.app.observe("MTR-GEN-002", "BR-204")                                                              # new evidence, accepted by a rebuild
        self.reader.rebuild()
        self.app.close()
        a = sqlite3.connect(str(old)); b = sqlite3.connect(str(self.path)); a.backup(b); a.close(); b.close()   # restore the backup over the live file
        self.app = Manufacturing(self.path)
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "ROLLBACK_OR_CONFIGURATION_REWRITE"):
            self.reader.rebuild()

    def test_coherent_forged_rewrite_is_caught_in_process_and_accepted_after_restart(self):
        """Documented limitation, pinned: an internally consistent replacement history is caught by the accepted-hash rule only while the reader remembers what it
        accepted. A restarted reader has no memory and no external anchor; that gap is unchanged by this design."""
        forged = self.dir / "forged.sqlite"
        f = Manufacturing(forged)
        f.create_unit("MTR-GEN-001"); f.assemble("MTR-GEN-001", "BR-310", "BR-312"); f.record_historical_shipment_fixture("MTR-GEN-001")
        f.close()
        src = sqlite3.connect(str(forged)); con = self.raw(); self.drop_guards(con)
        self.assertEqual(src.execute("SELECT config FROM motors").fetchone()[0], con.execute("SELECT config FROM motors WHERE serial='MTR-GEN-001'").fetchone()[0])
        con.execute("DELETE FROM events WHERE motor='MTR-GEN-001'")
        for row in src.execute("SELECT hash,raw,received FROM captures").fetchall():
            con.execute("INSERT OR REPLACE INTO captures VALUES(?,?,?)", row)
        for row in src.execute("SELECT id,motor,source,seq,native,epcis,capture,previous,hash FROM events ORDER BY ordinal").fetchall():
            con.execute("INSERT INTO events(id,motor,source,seq,native,epcis,capture,previous,hash) VALUES(?,?,?,?,?,?,?,?,?)", row)
        src.close()
        with self.assertRaisesRegex(ImpactUnavailable, "ROLLBACK_OR_CONFIGURATION_REWRITE"):
            self.reader.rebuild()
        fresh = ImpactQuery(self.path); self.addCleanup(fresh.close)
        fresh.rebuild()                                                                                        # accepted: nothing to compare with
        hit = [m for m in fresh.query("BR-204")["motors"] if m["motorSerial"] == "MTR-GEN-001"]
        self.assertTrue(not hit or not hit[0]["matchingEvidence"])


class SharedStateCannotBeHiddenByPerMotorCaching(Base):
    def registry(self, edit=None):
        document = json.loads(Path("application/lot_registry.synthetic.json").read_text(encoding="utf-8"))
        if edit:
            edit(document)
        path = self.dir / "registry.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_registry_change_reverifies_every_motor_and_changes_resolution(self):
        path = self.registry()
        reader = ImpactQuery(self.path, registry=path); self.addCleanup(reader.close)
        reader.rebuild()
        before = reader.query("ZZ-204")
        self.assertEqual(before["canonicalLot"], None)                                                         # unknown identity: the whole fleet, never a negative
        self.assertEqual(len(before["motors"]), 4)

        def alias(document):
            next(e for e in document["entries"] if e["canonical"] == "BR-204")["aliases"].append("ZZ-204")
        self.registry(alias)
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED"):
            reader.query("ZZ-204")
        info = reader.rebuild()
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (4, 0))                               # no motor's memo survives a registry change
        after = reader.query("ZZ-204")
        self.assertEqual(after["canonicalLot"], "BR-204")
        self.assertNotEqual(after["motors"], before["motors"])

    def test_fleet_membership_change_is_never_hidden_and_reverifies_only_the_new_motor(self):
        self.app.create_unit("MTR-GEN-005")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        info = self.reader.rebuild()
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (1, 4))
        self.assertIn("MTR-GEN-005", {m["motorSerial"] for m in self.reader.query("BR-204")["motors"]})
        con = self.raw()
        con.execute("DELETE FROM app_units WHERE serial='MTR-GEN-005'")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "FLEET_MEMBERSHIP_MISMATCH"):
            self.reader.rebuild()
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
            self.reader.query("BR-204")

    def test_recall_policy_state_is_not_read_and_not_hidden(self):
        before = self.answers()
        self.app.announce("BR-204", ["DE"]); self.app.snapshot()
        strip = lambda answers: {lot: {k: v for k, v in r.items() if k != "contentDigest"} for lot, r in answers.items()}
        self.assertEqual(strip(self.answers()), strip(before))                                                # the exposure index does not depend on the recall policy
        self.assertEqual(self.reader.rebuild()["motorsVerified"], 0)

    def test_memo_is_keyed_by_content_not_by_serial_alone(self):
        self.app.observe("MTR-GEN-002", "BR-204")
        info = self.reader.rebuild()
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (1, 3))
        self.assertTrue(self.reader._rows["MTR-GEN-002"]["observationEvidence"])


class IncrementalRebuild(Base):
    def test_one_changed_motor_verifies_exactly_one_motor_once(self):
        self.app.observe("MTR-GEN-004", "BR-204")
        real = Ledger._verified_rows
        calls = []
        with patch.object(Ledger, "_verified_rows", autospec=True, side_effect=lambda self, m: (calls.append(m), real(self, m))[1]):
            info = self.reader.rebuild()
        self.assertEqual(calls, ["MTR-GEN-004"])
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (1, 3))

    def test_cold_rebuild_verifies_each_motor_once_not_twice(self):
        real = Ledger._verified_rows
        calls = []
        fresh = ImpactQuery(self.path); self.addCleanup(fresh.close)
        with patch.object(Ledger, "_verified_rows", autospec=True, side_effect=lambda self, m: (calls.append(m), real(self, m))[1]):
            fresh.rebuild()
        self.assertEqual(sorted(calls), sorted(MOTORS))

    def test_warm_query_never_verifies(self):
        with patch.object(Ledger, "_verified_rows", side_effect=AssertionError("warm path must not decode")):
            for lot in LOTS:
                self.reader.query(lot)

    def test_incremental_projection_equals_a_cold_rebuild_after_random_operations(self):
        rnd = random.Random(2610)
        created = 0
        for step in range(14):
            op = rnd.choice(("observe", "observe", "create", "replace", "tick", "announce"))
            try:
                if op == "observe":
                    self.app.observe(rnd.choice(MOTORS[:3]), rnd.choice(("BR-204", "BR-310", "BR-2O4", "NSB-204")))
                elif op == "create":
                    created += 1; serial = f"MTR-GEN-1{created:02d}"
                    self.app.create_unit(serial)
                    if rnd.random() < .6:
                        self.app.assemble(serial, rnd.choice(("BR-204", "BR-310")), "BR-312")
                elif op == "replace" and step % 5 == 0:
                    self.app.replace(rnd.choice(MOTORS[:2]), "BR-310")
                elif op == "tick":
                    self.app.tick()
                elif op == "announce":
                    self.app.announce("BR-204", ["DE"])
            except ValidationFailure:
                continue
            self.reader.rebuild()
            fresh = ImpactQuery(self.path); self.addCleanup(fresh.close)
            fresh.rebuild()
            self.assertEqual(self.answers(), self.answers(fresh), (step, op))
            self.assertEqual({m: v[2] for m, v in self.reader._memo.items()}, {m: v[2] for m, v in fresh._memo.items()}, (step, op))


class StaleAndConcurrentGenerations(Base):
    def writer(self, motor="MTR-GEN-002", lot="BR-204"):
        errors = []

        def write():
            app = Manufacturing(self.path)
            try:
                app.observe(motor, lot)
            except Exception as exc:
                errors.append(exc)
            finally:
                app.close()
        t = threading.Thread(target=write); t.start(); t.join(30)
        self.assertFalse(t.is_alive()); self.assertFalse(errors)

    def test_commit_during_rebuild_is_never_presented_as_current(self):
        real = impact_query.verify_motor
        fired = []

        def racing(*args):
            if not fired:
                fired.append(1); self.writer()
            return real(*args)
        self.app.observe("MTR-GEN-004", "BR-204")                                                              # something to verify, so the hook runs
        with patch.object(impact_query, "verify_motor", side_effect=racing):
            self.reader.rebuild()
        generation = self.reader.generation
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED_REBUILD_REQUIRED"):
            self.reader.query("BR-204")                                                                        # the published index predates the commit: refused
        self.assertIsNone(self.reader.generation); self.assertIsNotNone(generation)
        self.reader.rebuild()
        self.assertTrue(self.reader.query("BR-204")["motors"])

    def test_commit_between_digest_and_response_is_a_consistent_snapshot_then_stale(self):
        original = self.reader._content_key

        def key(registry):
            result = original(registry); self.writer(); return result
        with patch.object(self.reader, "_content_key", side_effect=key):
            self.assertEqual(self.reader.query("BR-204")["totalMotors"], 4)
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED"):
            self.reader.query("BR-204")

    def test_serialized_payload_cannot_cross_a_generation(self):
        first = self.reader.query_json("BR-204")
        self.app.observe("MTR-GEN-004", "BR-204")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query_json("BR-204")
        self.reader.rebuild()
        second = self.reader.query_json("BR-204")
        self.assertNotEqual(first, second)
        self.assertEqual(json.loads(second)["evidenceGeneration"], self.reader.generation)

    def test_response_names_its_proofs(self):
        r = self.reader.query("BR-204")
        self.assertEqual((r["evidenceGeneration"], r["contentDigest"]), (self.reader.generation, self.reader._key))
        self.assertEqual(r["integrity"], "FULL_IMAGE_PROOF_EVERY_REQUEST_EVIDENCE_GENERATION_ON_MISMATCH")
        self.assertEqual(r["operationalClearance"], "NOT_ASSESSED")


class NoPrivateInternals(Base):
    def test_sources_use_no_private_ledger_state(self):
        for name in ("impact_query.py", "evidence_scope.py"):
            text = (Path(__file__).parent / name).read_text(encoding="utf-8")
            code = "\n".join(l.split("#")[0] for l in text.splitlines())
            for forbidden in ("object.__new__", "._config(", "._config ", "_verified_rows", ".watermark("):
                self.assertNotIn(forbidden, code, (name, forbidden))
        self.assertTrue(issubclass(ReadOnlyLedger, Ledger))

    def test_reader_refuses_an_unreviewed_ledger_or_profile(self):
        fake = type("H", (), {"hexdigest": lambda self: "0" * 64})()
        with patch.object(impact_query, "_PINS_OK", False), patch.object(impact_query.hashlib, "sha256", lambda data=b"": fake):
            with self.assertRaisesRegex(ImpactUnavailable, "READER_PIN_MISMATCH"):
                ImpactQuery(self.path)

    def test_the_reader_connection_cannot_write(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.reader.db.execute("DELETE FROM app_units")
        self.reader.db.rollback()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.reader.rebuild(); self.reader.query("BR-204")
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)


NON_EVIDENCE = {          # every other table of the ledger database, with the reason it cannot change exposure, genealogy or impact output
    "app_clock": "application clock: stamps new commands, never read by verification or projection",
    "decision_runs": "issued evaluator decisions: outputs of the evaluator, not inputs to exposure or genealogy",
    "recall_announcements": "recall policy versions: inputs to evaluator verdicts, not to the exposure index",
    "app_ship_tickets": "single-use shipment tickets: consumed by the shipment gate only",
    "app_audit": "application audit chain: records what happened, never read by verification or projection",
    "app_audit_head": "audit chain head",
}
DECISION_INPUTS = {"decision_runs", "recall_announcements", "app_clock", "app_audit", "app_audit_head", "app_ship_tickets"}


class InputSurface(unittest.TestCase):
    """Every database input capable of influencing exposure, genealogy or impact output is inside the evidence scope; everything else is enumerated and shown inert."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pramaan-surface-", ignore_cleanup_errors=True)
        cls.path = Path(cls.temp.name) / "ledger.sqlite"
        cls.app = build(cls.path)
        cls.app.announce("BR-204", ["DE"]); cls.app.snapshot()                                                  # populate decision/announcement/audit state too

    @classmethod
    def tearDownClass(cls):
        cls.app.close(); cls.temp.cleanup()

    def reads(self, action):
        seen = set()

        def authorizer(code, a1, a2, db, src):
            if code == sqlite3.SQLITE_READ and a1 not in ("sqlite_master", "sqlite_schema"):
                seen.add((a1, a2))
            return sqlite3.SQLITE_OK
        self.app.db.set_authorizer(authorizer)
        try:
            action()
        finally:
            self.app.db.set_authorizer(None)
        return seen

    def test_every_table_in_the_database_is_classified(self):
        tables = {r[0] for r in self.app.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        self.assertEqual(tables, set(scope.SCOPE) | set(NON_EVIDENCE), "a new table must be put in the evidence scope or justified as inert")
        self.assertFalse(set(scope.SCOPE) & set(NON_EVIDENCE))
        self.assertEqual(self.app.db.execute("SELECT count(*) FROM sqlite_master WHERE type='view'").fetchone()[0], 0)

    def test_exposure_and_genealogy_reads_stay_inside_the_scope(self):
        def run():
            for (motor,) in self.app.db.execute("SELECT serial FROM app_units").fetchall():
                wm = self.app.ledger.watermark(motor)
                self.app.ledger.snapshot(motor, wm)
                self.app.ledger.genealogy(motor, wm)
        seen = self.reads(run)
        self.assertTrue(seen)
        for table, column in seen:
            self.assertIn(table, scope.SCOPE, (table, column))
            self.assertTrue(column == "" or column in scope.SCOPE[table], (table, column))

    def test_the_full_evaluation_reads_only_scope_tables_plus_documented_decision_inputs(self):
        seen = self.reads(lambda: self.app.snapshot())
        tables = {t for t, _ in seen}
        self.assertTrue(set(scope.SCOPE) & tables)
        self.assertLessEqual(tables - set(scope.SCOPE), DECISION_INPUTS, "the evaluator reads a table that is neither evidence nor a documented decision input")

    def test_scope_columns_are_exactly_the_schema_columns(self):
        for table, columns in scope.SCOPE.items():
            real = [r[1] for r in self.app.db.execute(f"PRAGMA table_info({table})")]
            self.assertEqual(list(columns), real, table)

    def test_writes_to_every_inert_table_leave_the_impact_output_unchanged(self):
        copy = Path(self.temp.name) / "inert.sqlite"
        src = sqlite3.connect(str(self.path)); dst = sqlite3.connect(str(copy)); src.backup(dst); src.close()
        for (name,) in dst.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            dst.execute(f'DROP TRIGGER "{name}"')
        dst.commit()
        reader = ImpactQuery(copy)
        try:
            reader.rebuild()
            before = {lot: reader.query(lot) for lot in LOTS}
            dst.execute("UPDATE app_clock SET at='2030-01-01T00:00:00Z'")
            dst.execute("INSERT INTO recall_announcements VALUES(99,'{}','h')")
            dst.execute("INSERT INTO app_ship_tickets VALUES('MTR-GEN-004','x')")
            dst.execute("INSERT INTO decision_runs(motor,policy_hash,payload,hash) VALUES('MTR-GEN-001','p','{}','h')")
            dst.execute("INSERT INTO app_audit VALUES(9999,'X','{}','p','h')")
            dst.execute("UPDATE app_audit_head SET count=count+1")
            dst.commit()
            self.assertEqual(set(NON_EVIDENCE), {"app_clock", "recall_announcements", "app_ship_tickets", "decision_runs", "app_audit", "app_audit_head"})
            with patch.object(impact_query, "verify_motor", side_effect=AssertionError("must not re-verify")):
                after = {lot: reader.query(lot) for lot in LOTS}
            strip = lambda answers: {lot: {k: v for k, v in r.items() if k != "contentDigest"} for lot, r in answers.items()}
            self.assertEqual(strip(after), strip(before))
            self.assertEqual(reader.stats["reAnchors"], 1)
        finally:
            reader.close(); dst.close()


class WalBehaviour(Base):
    def test_a_wal_only_harmless_write_is_reanchored_without_touching_the_main_file(self):
        self.app.db.execute("PRAGMA wal_autocheckpoint=0")
        self.app.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.reader.rebuild()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.app.tick()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)                           # the change lives only in the WAL
        self.assertGreater(Path(str(self.path) + "-wal").stat().st_size, 0)
        self.reader.query("BR-204")
        self.assertEqual(self.reader.stats["reAnchors"], 1)

    def test_a_wal_only_evidence_write_is_rejected(self):
        self.app.db.execute("PRAGMA wal_autocheckpoint=0")
        self.app.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.reader.rebuild()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.app.observe("MTR-GEN-002", "BR-204")
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertStale()

    def test_checkpointing_after_an_evidence_write_cannot_make_the_old_projection_current(self):
        self.app.observe("MTR-GEN-002", "BR-204")
        self.raw().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.assertStale()

    def test_a_reader_transaction_sees_one_snapshot_while_a_writer_commits(self):
        self.reader.db.execute("BEGIN")
        try:
            self.reader.db.execute("SELECT count(*) FROM events").fetchone()
            self.app.observe("MTR-GEN-002", "BR-204")
            inside = self.reader.db.execute("SELECT count(*) FROM events").fetchone()[0]
            self.assertEqual(inside, self.reader._event_count)                                                  # still the pre-commit snapshot
        finally:
            self.reader.db.rollback()
        self.assertStale()

    def test_wal_mode_reassertion_and_restart_checkpoint_by_another_connection_is_harmless(self):
        self.app.close()
        con = self.raw()
        con.execute("PRAGMA journal_mode=WAL"); con.execute("PRAGMA wal_checkpoint(RESTART)")
        self.app = Manufacturing(self.path)
        self.reader.query("BR-204")
        self.assertLessEqual(self.reader.stats["reAnchors"], 1)


class ConcurrentWrites(Base):
    def commit(self, evidence, motor="MTR-GEN-002"):
        errors = []

        def write():
            app = Manufacturing(self.path)
            try:
                app.observe(motor, "BR-204") if evidence else app.tick()
            except Exception as exc:
                errors.append(exc)
            finally:
                app.close()
        t = threading.Thread(target=write); t.start(); t.join(30)
        self.assertFalse(t.is_alive()); self.assertFalse(errors)

    def test_harmless_commit_during_verification_leaves_a_usable_published_projection(self):
        real = impact_query.verify_motor
        fired = []

        def racing(*args):
            if not fired:
                fired.append(1); self.commit(False)
            return real(*args)
        self.app.observe("MTR-GEN-004", "BR-204")
        with patch.object(impact_query, "verify_motor", side_effect=racing):
            self.reader.rebuild()
        self.assertTrue(fired)
        self.reader.query("BR-204")                                                                             # re-anchored, still current
        self.assertEqual(self.reader.stats["reAnchors"], 1)

    def test_evidence_commit_during_verification_is_never_presented_as_current(self):
        real = impact_query.verify_motor
        fired = []

        def racing(*args):
            if not fired:
                fired.append(1); self.commit(True)
            return real(*args)
        self.app.observe("MTR-GEN-004", "BR-204")
        with patch.object(impact_query, "verify_motor", side_effect=racing):
            self.reader.rebuild()
        self.assertTrue(fired)
        self.assertStale()
        self.reader.rebuild()
        self.assertTrue(self.reader.query("BR-204")["motors"])

    def test_evidence_commit_between_publication_and_first_use_is_refused(self):
        self.commit(True)
        self.reader.rebuild()
        self.commit(True, "MTR-GEN-004")                                                                         # after publication, before any query
        self.assertStale()

    def test_evidence_commit_inside_the_decision_of_a_mismatch_is_judged_on_its_snapshot_then_refused(self):
        self.commit(False)                                                                                       # forces the slow path
        original = self.reader._generation

        def generation(registry):
            result = original(registry); self.commit(True); return result
        with patch.object(self.reader, "_generation", side_effect=generation):
            self.assertEqual(self.reader.query("BR-204")["totalMotors"], 4)                                      # consistent as of its snapshot
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED"):
            self.reader.query("BR-204")

    def test_two_writers_and_a_reader_never_serve_a_stale_or_future_projection(self):
        stop = threading.Event(); committed = []; errors = []

        def writer(evidence):
            app = Manufacturing(self.path)
            try:
                for i in range(6):
                    if evidence:
                        app.observe(MOTORS[i % 3], "BR-204")
                    else:
                        app.tick()
                    committed.append(evidence)
                    stop.wait(.05)
            except Exception as exc:
                errors.append(exc)
            finally:
                app.close()
        threads = [threading.Thread(target=writer, args=(True,)), threading.Thread(target=writer, args=(False,))]
        for t in threads:
            t.start()
        counts, codes = [], set()
        while any(t.is_alive() for t in threads):
            try:
                counts.append(self.reader.query("BR-204")["eventCount"])
            except ImpactUnavailable as exc:
                codes.add(exc.code)
                if exc.code in ("EVIDENCE_CHANGED_REBUILD_REQUIRED", "VERIFIED_INDEX_REQUIRED"):
                    try:
                        self.reader.rebuild()
                    except ImpactUnavailable as exc2:
                        codes.add(exc2.code)
        for t in threads:
            t.join(30)
        self.assertFalse(errors)
        self.assertLessEqual(codes, {"EVIDENCE_CHANGED_REBUILD_REQUIRED", "VERIFIED_INDEX_REQUIRED"})
        self.assertEqual(counts, sorted(counts))                                                                 # a served projection never goes backwards
        total = self.raw().execute("SELECT count(*) FROM events").fetchone()[0]
        self.assertTrue(all(c <= total for c in counts))
        try:
            final = self.reader.query("BR-204")
        except ImpactUnavailable:
            self.reader.rebuild(); final = self.reader.query("BR-204")
        self.assertEqual(final["eventCount"], total)


class RestartAndTampering(Base):
    def test_a_restarted_reader_has_no_memory_and_verifies_everything(self):
        fresh = ImpactQuery(self.path); self.addCleanup(fresh.close)
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
            fresh.query("BR-204")
        info = fresh.rebuild()
        self.assertEqual((info["motorsVerified"], info["motorsReused"]), (4, 0))
        self.assertEqual(self.answers(fresh), self.answers())

    def test_malformed_and_tampered_evidence_fails_closed_without_a_crash(self):
        cases = {
            "native not JSON": "UPDATE events SET native='{' WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "native emptied": "UPDATE events SET native='' WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "native as BLOB": "UPDATE events SET native=CAST(native AS BLOB) WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "epcis emptied": "UPDATE events SET epcis='' WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "capture truncated": "UPDATE captures SET raw=substr(raw,1,40) WHERE hash=(SELECT capture FROM events WHERE motor='MTR-GEN-001' LIMIT 1)",
            "capture as TEXT": "UPDATE captures SET raw=CAST(raw AS TEXT) WHERE hash=(SELECT capture FROM events WHERE motor='MTR-GEN-001' LIMIT 1)",
            "seq as text": "UPDATE events SET seq='x' WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "huge id": "UPDATE events SET id=id||hex(zeroblob(2000000)) WHERE rowid=(SELECT min(rowid) FROM events WHERE motor='MTR-GEN-001')",
            "config not JSON": "UPDATE motors SET config='nope' WHERE serial='MTR-GEN-002'",
            "config JSON null": "UPDATE motors SET config='null' WHERE serial='MTR-GEN-002'",
            "motor hash NULLed by empty": "UPDATE motors SET hash='' WHERE serial='MTR-GEN-002'",
            "events reassigned to unknown motor": "UPDATE events SET motor='MTR-X' WHERE motor='MTR-GEN-003'",
            "capture row deleted": "DELETE FROM captures WHERE hash=(SELECT capture FROM events WHERE motor='MTR-GEN-001' LIMIT 1)",
        }
        for name, statement in cases.items():
            with self.subTest(name):
                self.setUp()
                con = self.raw(); self.drop_guards(con)
                con.execute(statement)
                try:
                    self.reader.query("BR-204")
                    self.fail("a tampered database was served as current: " + name)
                except ImpactUnavailable:
                    pass
                try:
                    self.reader.rebuild()
                except ImpactUnavailable as exc:
                    self.assertIn(exc.code, ("INPUT_VERIFICATION_FAILED", "FLEET_MEMBERSHIP_MISMATCH", "ROLLBACK_DETECTED", "ROLLBACK_OR_CONFIGURATION_REWRITE"), name)
                    with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
                        self.reader.query("BR-204")

    def test_a_tampered_database_never_turns_into_a_reanchor(self):
        self.app.tick()                                                                                           # forces the slow path
        con = self.raw(); self.drop_guards(con)
        con.execute("UPDATE events SET native=replace(native,'BR-204','BR-999') WHERE motor='MTR-GEN-001'")
        self.assertStale()
        self.assertEqual(self.reader.stats["reAnchors"], 0)


class MappedReads(Base):
    def test_a_mapped_reader_returns_what_an_unmapped_reader_returns(self):
        self.assertIn(self.reader._mmap_bytes, (0, impact_query.MMAP_BYTES))
        mapped = self.answers()
        self.reader.db.execute("PRAGMA mmap_size=0")
        self.assertEqual(self.answers(), mapped)

    def test_the_reader_closes_its_map_for_database_maintenance(self):
        before = self.answers()
        with self.reader.maintenance():
            self.app.close()
            con = sqlite3.connect(str(self.path), isolation_level=None)
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)"); con.execute("VACUUM"); con.close()
            os.replace(self.path, self.dir / "moved.sqlite")                                                      # no reader handle or mapping may block this
            os.replace(self.dir / "moved.sqlite", self.path)
        self.app = Manufacturing(self.path)
        strip = lambda answers: {lot: {k: v for k, v in r.items() if k != "contentDigest"} for lot, r in answers.items()}
        self.assertEqual(strip(self.answers()), strip(before))                                                    # same evidence: re-anchored, not rebuilt

    def test_maintenance_that_changes_evidence_is_refused(self):
        with self.reader.maintenance():
            self.app.observe("MTR-GEN-002", "BR-204")
        self.assertStale()

    def test_close_releases_the_file_and_the_reader_stays_closed(self):
        self.app.close()
        self.reader.close()
        os.replace(self.path, self.dir / "moved.sqlite")
        os.replace(self.dir / "moved.sqlite", self.path)
        with self.assertRaises(ImpactUnavailable) as ctx:
            self.reader.query("BR-204")
        self.assertIn(ctx.exception.code, ("VERIFIED_INDEX_REQUIRED", "INPUT_VERIFICATION_FAILED"))
        self.reader.close()                                                                                       # idempotent


if __name__ == "__main__":
    unittest.main()
