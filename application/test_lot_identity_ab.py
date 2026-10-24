"""Candidate A+B: adversarial, bypass, registry-change, interrupted-operation, API and checkpoint-review tests (disposable synthetic DBs, loopback only).
Run: python -B -m unittest application.test_lot_identity_ab -v
Set LOT_AB_EVIDENCE=<file> to write the measured matrix/evidence as JSON. Negative reproductions of the v1.0 defect live in research/lot_identity_ab/reproduce_v1_0.py
(they need the frozen tag's source and run it unmodified).
"""
import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import lot_identity as lots
from . import server as server_mod
from . import checkpoint_ops
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .service import Manufacturing, PART, ValidationFailure, LedgerBlocked

EVIDENCE = {}
M = "MTR-90001"
RECALLED, SAFE = "BR-204", "BR-310"
BAD = [("missing", None), ("empty", ""), ("whitespace", "   "), ("UNKNOWN", "UNKNOWN"), ("unknown", "unknown"), ("N/A", "N/A"), ("dash", "-"), ("zero", "0"),
       ("lowercase", "br-204"), ("trailing-space", "BR-204 "), ("letter-O", "BR-2O4"), ("en-dash", "BR–204"), ("zero-width", "BR-204​"),
       ("no-dash", "BR204"), ("transposed", "BR-240"), ("full-width", "ＢＲ-204"), ("unregistered-wellformed", "BR-999"),
       ("malformed", "foo bar"), ("withdrawn", "BR-420"), ("overlong", "B" * 81)]
GOOD_UNAFFECTED = [("BR-310", "BR-310"), ("BR-312", "BR-312"), ("BR-901", "BR-901"), ("adjacent-BR-205", "BR-205"), ("adjacent-BR-311", "BR-311")]
SCOPES = {"scoped DE": ["DE"], "scoped NDE": ["NDE"], "scoped both": ["DE", "NDE"], "unspecified": None}
_n = [0]


def registry_with(mutate=None):
    doc = json.loads(lots.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    if mutate:
        mutate(doc)
    return lots.LotRegistry(doc)


def entry(canonical, supplier="SUP-KAV-02", name="Kaveri Precision — synthetic supplier", **kw):
    e = dict(canonical=canonical, part=PART, issuer="MANUFACTURER-LOCAL-SYNTHETIC-REGISTRY", provenance=lots.PROVENANCE, aliases=[], effectiveFrom="2026-01-01T00:00:00Z",
             effectiveTo=None, status="ACTIVE", supplierId=supplier, supplierName=name, rawMaterialLot="STEEL-26-518")
    e.update(kw)
    return e


def new_app(d, registry=None, name="m.sqlite"):
    app = Manufacturing(Path(d) / name, lot_registry=registry)
    return app


def current(app, d):
    _n[0] += 1
    a = Path(d) / f"anchor{_n[0]}.json"
    app.snapshot()
    publish_candidate(a, export_anchor(app))
    return app.snapshot(trusted_anchor=TrustedAnchor(a))


def raw_assemble(app, motor, de, nde, identity="SERIAL"):
    """Bypass: the v1.0 capture sequence with NO lot validation and the v1.0 hard-coded supplier rule (models legacy / bypassed captures)."""
    build = f"BUILD-{motor}"
    app.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), work_order=build)
    for slot, lot in (("DE", de), ("NDE", nde)):
        serial = f"BRG-{motor}-{slot}-01" if identity == "SERIAL" else None
        nsb = lot == "BR-204"
        a = app.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410" if nsb else "STEEL-26-518", supplierId="SUP-NSB-01" if nsb else "SUP-KAV-02", supplierName="x"))
        made = app.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(rawMaterialLot=a["payload"]["rawMaterialLot"], supplierId=a["payload"]["supplierId"], part=PART, lot=lot, serial=serial, materialEventId=a["eventId"]))
        pl = dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity=identity, manufacturingEventId=made["eventId"])
        if serial:
            pl["serial"] = serial
        app.event(motor, "COMPONENT_INSTALLED", "ASSY", pl, work_order=build)
    app.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=build)


def decision(snap, motor=M):
    return next(iter(snap["decisions"][motor].values()))["current"]


def summarize(snap, motor=M):
    c = decision(snap, motor)
    return dict(checkpoint=snap["checkpoint"]["state"], eligible=snap["eligibility"][motor]["currentReleaseEligible"], finding=c["evidenceFinding"],
                evaluatorAction=c["evaluatorOperationalAction"], action=c["operationalAction"], guard=c["identityGuard"]["status"],
                reasons=sorted({f["reason"] for f in c["identityGuard"]["findings"]}))


class Capture(unittest.TestCase):
    """Positive registry membership at capture: nothing malformed is ever written; registered lots are not held."""

    def run_case(self, d, path, lot, slot, scope, registry=None):
        app = new_app(d, registry, f"c{_n[0]}.sqlite"); _n[0] += 1
        r = dict(path=path, slot=slot, scope=scope)
        try:
            app.create_unit(M)
            before = None
            try:
                if path == "assemble":
                    app.assemble(M, *((lot, SAFE) if slot == "DE" else (SAFE, lot)))
                elif path == "replace":
                    app.assemble(M, RECALLED, SAFE); before = len(app.events(M)); app.replace(M, lot)
                else:
                    app.assemble(M, SAFE, SAFE); before = len(app.events(M)); app.observe(M, lot)
                r["capture"] = "ACCEPTED"
            except ValidationFailure as e:
                r["capture"] = "REJECTED"; r["why"] = str(e)[:100]
                r["eventsWritten"] = len(app.events(M)) - (before or 0)
            if path != "assemble" or r["capture"] == "ACCEPTED":
                app.ship(M)
            app.announce(RECALLED, SCOPES[scope])
            r["result"] = summarize(current(app, d))
        finally:
            app.close()
        return r

    def test_matrix_bad_lots_never_clear_and_leave_no_residue(self):
        rows = []
        with tempfile.TemporaryDirectory() as d:
            for scope in SCOPES:
                for name, lot in BAD:
                    for slot in ("DE", "NDE"):
                        rows.append(self.run_case(d, "assemble", lot, slot, scope) | dict(lotCase=name))
            for scope in ("scoped DE", "unspecified"):
                for name, lot in BAD:
                    for path in ("replace", "observe"):
                        rows.append(self.run_case(d, path, lot, "DE", scope) | dict(lotCase=name))
        EVIDENCE["badLotMatrix"] = rows
        for r in rows:
            self.assertEqual(r["capture"], "REJECTED", r)            # every malformed/unregistered/withdrawn lot is refused at capture
            self.assertEqual(r["eventsWritten"], 0, r)                 # and nothing was written before the refusal
            if r["path"] == "assemble":
                self.assertFalse(r["result"]["eligible"], r)
        EVIDENCE["badLotCases"] = len(rows)

    def test_registered_lots_incl_adjacent_are_not_held(self):
        rows, false_holds = [], []
        with tempfile.TemporaryDirectory() as d:
            for scope in SCOPES:
                for name, lot in GOOD_UNAFFECTED:
                    for slot in ("DE", "NDE"):
                        r = self.run_case(d, "assemble", lot, slot, scope) | dict(lotCase=name)
                        rows.append(r)
                        if not r["result"]["eligible"]:
                            false_holds.append(r)
                    for path in ("replace", "observe"):
                        r = self.run_case(d, path, lot, "DE", scope if scope in ("scoped DE", "unspecified") else "scoped DE") | dict(lotCase=name)
                        rows.append(r)
                        if not r["result"]["eligible"]:
                            false_holds.append(r)
        EVIDENCE["registeredUnaffectedCases"] = len(rows); EVIDENCE["falseHoldsOnRegisteredUnaffected"] = len(false_holds)
        self.assertEqual(false_holds, [])                            # no unintended hold on legitimate registered lots, including BR-205 beside recalled BR-204
        with tempfile.TemporaryDirectory() as d:                      # and the recalled lot still holds
            for scope, slot, want in (("scoped DE", "DE", False), ("unspecified", "NDE", False), ("scoped NDE", "DE", True)):
                r = self.run_case(d, "assemble", RECALLED, slot, scope)
                self.assertEqual(r["result"]["eligible"], want, r)

    def test_alias_is_stored_canonical_and_judged_as_recalled(self):
        with tempfile.TemporaryDirectory() as d:
            app = new_app(d); app.create_unit(M); app.assemble(M, "NSB-204", SAFE); app.ship(M); app.announce(RECALLED, ["DE"])
            inst = [e for e in app.events(M) if e["eventType"] == "COMPONENT_INSTALLED"]
            self.assertEqual([e["payload"]["lot"] for e in inst], [RECALLED, SAFE])
            s = summarize(current(app, d)); app.close()
            self.assertEqual((s["finding"], s["eligible"]), ("AFFECTED", False))

    def test_supplier_scope_comes_from_registry(self):
        with tempfile.TemporaryDirectory() as d:
            app = new_app(d, registry_with(lambda doc: doc["entries"].append(entry("BR-401", "SUP-NSB-01", "Northstar Bearings — synthetic supplier", rawMaterialLot="STEEL-26-410"))))
            app.create_unit(M); app.assemble(M, "BR-401", SAFE)
            sup = {e["payload"]["lot"]: e["payload"]["supplierId"] for e in app.events(M) if e["eventType"] == "BEARING_MANUFACTURED"}
            app.close()
        self.assertEqual(sup["BR-401"], "SUP-NSB-01")

    def test_conflicting_aliases_and_supplier_scopes_refuse(self):
        def alias_clash(doc):
            doc["entries"][1]["aliases"] = ["X-1"]; doc["entries"][2]["aliases"] = ["X-1"]
        def supplier_clash(doc):
            doc["entries"].append(entry("BR-310", "SUP-OTHER-09", "Other supplier — synthetic"))
        def alias_is_canonical(doc):
            doc["entries"][1]["aliases"] = ["BR-312"]
        for mut, lot, reason in ((alias_clash, "X-1", "ALIAS_CONFLICT"), (supplier_clash, "BR-310", "AMBIGUOUS_SUPPLIER_SCOPE"), (alias_is_canonical, "BR-312", "ALIAS_CONFLICT")):
            reg = registry_with(mut)
            self.assertEqual(reg.resolve(lot).status, reason)
            with tempfile.TemporaryDirectory() as d:
                app = new_app(d, reg); app.create_unit(M)
                with self.assertRaises(ValidationFailure) as cm:
                    app.assemble(M, lot, SAFE)
                self.assertIn(reason, str(cm.exception)); self.assertEqual(len(app.events(M)), 0)
                app.close()

    def test_resembles_is_only_an_investigation_hint(self):
        reg = registry_with()
        r = reg.resolve("BR-2O4")
        self.assertEqual(r.status, "UNREGISTERED"); self.assertIn("BR-204", r.resembles)
        self.assertEqual(reg.resolve("BR-205").status, "REGISTERED")      # adjacent registered lot: never reclassified by look-alike logic
        self.assertEqual(reg.resolve("BR-205").resembles, ())


class ReadSide(unittest.TestCase):
    """Legacy and bypassed records: identity is checked wherever the record came from; the evaluator's finding stays visible and separate."""

    def bypass(self, d, de, nde, scope="scoped DE", registry=None):
        app = new_app(d, registry, f"b{_n[0]}.sqlite"); _n[0] += 1
        try:
            app.create_unit(M); raw_assemble(app, M, de, nde); app.ship(M); app.announce(RECALLED, SCOPES[scope])
            return summarize(current(app, d)), current(app, d)
        finally:
            app.close()

    def test_bypassed_bad_lots_are_held_and_reported_separately(self):
        rows = []
        bad = [(n, l) for n, l in BAD if isinstance(l, str) and l.strip() and len(l) <= 80 and l != "BR-420"]
        with tempfile.TemporaryDirectory() as d:
            for scope in ("scoped DE", "scoped NDE", "unspecified"):
                for name, lot in bad + [("withdrawn", "BR-420"), ("alias-literal", "NSB-204")]:
                    for slot in ("DE", "NDE"):
                        s, snap = self.bypass(d, *((lot, SAFE) if slot == "DE" else (SAFE, lot)), scope=scope)
                        rows.append(dict(lotCase=name, slot=slot, scope=scope, **s))
                        self.assertFalse(s["eligible"], rows[-1])
                        self.assertEqual(s["guard"], "IDENTITY_NOT_ESTABLISHED"); self.assertNotEqual(s["action"], "RELEASE_ELIGIBLE")
                        if s["evaluatorAction"] == "RELEASE_ELIGIBLE":     # the guard changed an evaluator release: both values are reported
                            self.assertEqual(s["finding"], "EXCLUDED_WITH_EVIDENCE"); self.assertEqual(s["action"], "RECALL_HOLD")
        EVIDENCE["bypassMatrix"] = rows; EVIDENCE["bypassCases"] = len(rows)
        self.assertGreater(sum(r["evaluatorAction"] == "RELEASE_ELIGIBLE" for r in rows), 40)      # the evaluator alone WOULD have released many of them

    def test_bypassed_registered_lots_are_not_held(self):
        with tempfile.TemporaryDirectory() as d:
            for name, lot in GOOD_UNAFFECTED:
                s, _ = self.bypass(d, lot, SAFE, "unspecified")
                self.assertTrue(s["eligible"], (name, s))

    def test_registry_change_after_capture_changes_read_side(self):
        with tempfile.TemporaryDirectory() as d:
            app = new_app(d); app.create_unit(M); app.assemble(M, SAFE, "BR-312"); app.ship(M); app.announce(RECALLED, ["DE"])
            self.assertTrue(summarize(current(app, d))["eligible"]); app.close()
            def withdraw(doc):
                next(e for e in doc["entries"] if e["canonical"] == SAFE)["status"] = "WITHDRAWN"
            app = Manufacturing(Path(d) / "m.sqlite", lot_registry=registry_with(withdraw))
            s = summarize(current(app, d)); app.close()
            self.assertEqual((s["eligible"], s["reasons"]), (False, ["WITHDRAWN"]))
            def expired(doc):
                next(e for e in doc["entries"] if e["canonical"] == SAFE)["effectiveTo"] = "2026-01-02T00:00:00Z"
            app = Manufacturing(Path(d) / "m.sqlite", lot_registry=registry_with(expired))
            s = summarize(current(app, d)); app.close()
            self.assertEqual((s["eligible"], s["reasons"]), (False, ["EXPIRED"]))
            def later(doc):
                next(e for e in doc["entries"] if e["canonical"] == SAFE)["effectiveFrom"] = "2027-01-01T00:00:00Z"
            app = Manufacturing(Path(d) / "m.sqlite", lot_registry=registry_with(later))
            s = summarize(current(app, d)); app.close()
            self.assertEqual((s["eligible"], s["reasons"]), (False, ["NOT_YET_EFFECTIVE"]))

    def test_supplier_scope_mismatch_and_unregistered_recall_lot(self):
        with tempfile.TemporaryDirectory() as d:
            # legacy rule attributed BR-310 to the Kaveri supplier; a registry saying Northstar owns it contradicts the recorded manufacture event
            s, _ = self.bypass(d, SAFE, "BR-312", "unspecified", registry_with(lambda doc: next(e for e in doc["entries"] if e["canonical"] == SAFE).update(supplierId="SUP-NSB-01", supplierName="x")))
            self.assertEqual((s["eligible"], s["reasons"]), (False, ["SUPPLIER_SCOPE_MISMATCH"]))
        with tempfile.TemporaryDirectory() as d:
            # a recall announced under a looser registry whose lot the current registry does not know: no exclusion anywhere can be trusted
            loose = registry_with(lambda doc: doc["entries"].append(entry("BR-777")))
            app = new_app(d, loose); app.create_unit(M); app.assemble(M, SAFE, "BR-312"); app.ship(M); app.announce("BR-777", ["DE"]); app.close()
            app = Manufacturing(Path(d) / "m.sqlite", lot_registry=registry_with())
            s = summarize(current(app, d)); app.close()
            self.assertEqual((s["eligible"], s["reasons"]), (False, ["UNREGISTERED"]))

    def test_repair_path_for_legacy_unknown_lot(self):
        """Documented limit: an unknown DE occupant can be replaced with a registered lot (then eligible); an unknown NDE occupant cannot be repaired in-app."""
        with tempfile.TemporaryDirectory() as d:
            app = new_app(d); app.create_unit(M); raw_assemble(app, M, "UNKNOWN", SAFE); app.ship(M); app.announce(RECALLED, ["DE"])
            self.assertFalse(summarize(current(app, d))["eligible"])
            app.replace(M, "BR-312")
            s = summarize(current(app, d)); app.close()
            EVIDENCE["repairUnknownDE"] = s
            self.assertTrue(s["eligible"], s)
        with tempfile.TemporaryDirectory() as d:
            app = new_app(d); app.create_unit(M); raw_assemble(app, M, SAFE, "UNKNOWN"); app.ship(M); app.announce(RECALLED, ["DE"])
            app.replace(M, "BR-312")                                    # replaces the DE bearing only
            s = summarize(current(app, d)); app.close()
            EVIDENCE["repairUnknownNDE"] = s
            self.assertFalse(s["eligible"], s); self.assertIn("SENTINEL", s["reasons"])

    def test_registry_unavailable_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(LedgerBlocked):
                Manufacturing(Path(d) / "m.sqlite", lot_registry=Path(d) / "missing.json")
            bad = Path(d) / "bad.json"; bad.write_text('{"entries": []}', encoding="utf-8")
            with self.assertRaises(LedgerBlocked):
                Manufacturing(Path(d) / "m.sqlite", lot_registry=bad)      # provenance not declared


class Interrupted(unittest.TestCase):
    def crash(self, d, op, k):
        app = new_app(d, None, f"i{_n[0]}.sqlite"); _n[0] += 1
        out = dict(op=op, crashAfterEvents=k)
        try:
            app.create_unit(M)
            if op == "replace":
                app.assemble(M, RECALLED, SAFE)
            before = len(app.events(M))
            real, n = app.ledger.capture, [0]
            def flaky(*a, **kw):
                if n[0] == k:
                    raise RuntimeError("injected crash")
                n[0] += 1
                return real(*a, **kw)
            app.ledger.capture = flaky
            try:
                app.assemble(M, SAFE, "BR-312") if op == "assemble" else app.replace(M, SAFE)
            except RuntimeError:
                pass
            app.ledger.capture = real
            out["eventsWritten"] = len(app.events(M)) - before
            try:
                app.assemble(M, SAFE, "BR-312") if op == "assemble" else app.replace(M, SAFE); out["retry"] = "ACCEPTED"
            except Exception as e:
                out["retry"] = type(e).__name__ + ": " + str(e)[:120]
            out["eventsAfterRetry"] = len(app.events(M)) - before
            app.announce(RECALLED, ["DE"])
            try:
                snap = current(app, d); out["state"] = summarize(snap)
            except Exception as e:
                out["state"] = "SNAPSHOT_BLOCKED " + type(e).__name__
        finally:
            app.close()
        return out

    def test_interrupted_operations_fail_closed_and_retry_is_refused_without_new_events(self):
        rows = []
        with tempfile.TemporaryDirectory() as d:
            for op, kmax in (("assemble", 8), ("replace", 6)):
                for k in range(kmax):
                    rows.append(self.crash(d, op, k))
        EVIDENCE["interruptedOperations"] = rows
        for r in rows:
            if r["eventsWritten"] == 0:
                self.assertTrue(r["retry"] == "ACCEPTED" or r["op"] == "replace", r)    # nothing written: clean retry (replace k=0: motor still on recalled lot)
                continue
            self.assertTrue(r["retry"].startswith("ValidationFailure"), r)                # refused up front
            self.assertEqual(r["eventsAfterRetry"], r["eventsWritten"], r)                # the retry wrote nothing: no LedgerBlocked path
            self.assertIsInstance(r["state"], dict, r)
            self.assertFalse(r["state"]["eligible"], r)
            self.assertIn("OPERATION_INTERRUPTED", r["state"]["reasons"], r)


class Api(unittest.TestCase):
    def serve(self, d, bypass=None):
        db, anchor = Path(d) / "h.sqlite", Path(d) / "a.json"
        app = Manufacturing(db); app.create_unit(M)
        if bypass:
            raw_assemble(app, M, *bypass); app.ship(M); app.announce(RECALLED, ["DE"])
        app.close()
        app = Manufacturing(db); publish_candidate(anchor, export_anchor(app)); app.close()
        srv = server_mod.make_server(db, 0, trusted_anchor=anchor)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_port}", db, anchor

    def post(self, base, tok, path, body):
        req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": tok})
        try:
            with urlopen(req) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def test_api_refuses_bad_lots_and_exposes_guard_consistently(self):
        out = {}
        with tempfile.TemporaryDirectory() as d:
            srv, base, db, anchor = self.serve(d)
            try:
                tok = json.load(urlopen(base + "/api/session"))["token"]
                extra = {"currentReleaseEligible": True, "eligibility": {M: {"currentReleaseEligible": True}}, "trusted": True, "identityGuard": {"status": "IDENTITY_ESTABLISHED_LOCAL_REGISTRY"}}
                for lot in ("UNKNOWN", "BR-2O4", "br-204", "BR-999", "BR-420"):
                    s, _ = self.post(base, tok, f"/api/units/{M}/assemble", {"deLot": lot, "ndeLot": SAFE, **extra})
                    self.assertEqual(s, 400, lot)
                out["assembleBad"] = 400
                self.assertEqual(self.post(base, tok, f"/api/units/{M}/assemble", {"deLot": "BR-205", "ndeLot": SAFE, **extra})[0], 200)
                self.post(base, tok, f"/api/units/{M}/ship", {})
                self.assertEqual(self.post(base, tok, "/api/recalls", {"lot": "N/A"})[0], 400)
                self.assertEqual(self.post(base, tok, "/api/recalls", {"lot": "BR-2O4", "affectedSlots": ["DE"]})[0], 400)
                self.assertEqual(self.post(base, tok, "/api/recalls", {"lot": RECALLED, "affectedSlots": ["DE"]})[0], 200)
                snap = json.load(urlopen(base + "/api/snapshot"))
                self.assertIn("lotIdentity", snap); self.assertEqual(snap["lotIdentity"]["registry"]["provenance"], lots.PROVENANCE)
                self.assertFalse(snap["eligibility"][M]["currentReleaseEligible"])            # extra body fields changed nothing; checkpoint not renewed
            finally:
                srv.shutdown(); srv.server_close()

    def test_guard_shared_by_snapshot_decisions_investigation_and_review(self):
        with tempfile.TemporaryDirectory() as d:
            srv, base, db, anchor = self.serve(d, bypass=("UNKNOWN", SAFE))
            try:
                snap = json.load(urlopen(base + "/api/snapshot"))
                dec = json.load(urlopen(base + f"/api/motors/{M}/decisions")) if snap["checkpoint"]["state"] == "ANCHORED_CURRENT" else None
                guard = decision(snap)["identityGuard"]
                self.assertEqual(guard["status"], "IDENTITY_NOT_ESTABLISHED")
                self.assertEqual(decision(snap)["evaluatorOperationalAction"], "RELEASE_ELIGIBLE"); self.assertEqual(decision(snap)["operationalAction"], "RECALL_HOLD")
                reasons_snapshot = sorted({f["reason"] for f in guard["findings"]})
            finally:
                srv.shutdown(); srv.server_close()
            # same facts through the checkpoint review for the same database
            prop = checkpoint_ops.propose(db, anchor, Path(d) / "custody")
            row = next(r for r in prop["review"]["rows"] if r["motor"] == M)
            self.assertEqual(sorted({f["reason"] for f in row["identityFindings"]}), reasons_snapshot)
            self.assertEqual(row["guardedAction"], "RECALL_HOLD"); self.assertEqual(row["evaluatorAction"], "RELEASE_ELIGIBLE")
            self.assertEqual(prop["review"]["refusedForIdentity"], [M])
            EVIDENCE["sharedSemantics"] = dict(snapshotReasons=reasons_snapshot, reviewReasons=sorted({f["reason"] for f in row["identityFindings"]}))


class CheckpointReview(unittest.TestCase):
    def setup(self, d, specs):
        db, c0, custody = Path(d) / "r.sqlite", Path(d) / "c0.json", Path(d) / "custody"
        app = Manufacturing(db)
        for m in specs:
            app.create_unit(m)
        app.close()
        app = Manufacturing(db); publish_candidate(c0, export_anchor(app)); app.close()
        app = Manufacturing(db)
        for m, (de, nde, raw) in specs.items():
            (raw_assemble if raw else lambda a, mm, x, y: a.assemble(mm, x, y))(app, m, de, nde); app.ship(m)
        app.announce(RECALLED, ["DE"]); app.close()
        return db, c0, custody

    def test_review_requires_ack_and_refuses_identity_unsafe_regardless(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = self.setup(d, {"MTR-90001": ("UNKNOWN", SAFE, True), "MTR-90002": (RECALLED, SAFE, False), "MTR-90003": (SAFE, "BR-312", False), "MTR-90004": ("BR-205", "BR-311", False)})
            prop = checkpoint_ops.propose(db, c0, custody)
            rv = prop["review"]; by = {r["motor"]: r for r in rv["rows"]}
            EVIDENCE["reviewRows"] = rv["rows"]
            self.assertTrue(by["MTR-90001"]["identityUnsafeExclusion"]); self.assertEqual(rv["refusedForIdentity"], ["MTR-90001"])
            self.assertTrue(by["MTR-90003"]["newlyExcluded"] and by["MTR-90003"]["newlyReleaseEligible"]); self.assertTrue(by["MTR-90004"]["newlyReleaseEligible"])
            self.assertFalse(by["MTR-90002"]["newlyExcluded"])
            self.assertEqual(rv["requiresAcknowledgement"], ["MTR-90003", "MTR-90004"])
            cand = Path(prop["candidate"])
            with self.assertRaises(SystemExit) as cm:                       # every motor acknowledged: still refused for identity
                checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90001", "MTR-90002", "MTR-90003", "MTR-90004"])
            self.assertIn("not established", str(cm.exception)); self.assertFalse((custody / "accepted").exists())

    def test_ack_required_for_legitimate_exclusions_and_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = self.setup(d, {"MTR-90003": (SAFE, "BR-312", False), "MTR-90004": ("BR-205", "BR-311", False), "MTR-90002": (RECALLED, SAFE, False)})
            prop = checkpoint_ops.propose(db, c0, custody); cand = Path(prop["candidate"])
            self.assertEqual(prop["review"]["refusedForIdentity"], [])
            with self.assertRaises(SystemExit) as cm:
                checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"])
            self.assertIn("acknowledged individually", str(cm.exception))
            with self.assertRaises(SystemExit):
                checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90003"])      # partial acknowledgement
            rec = checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90003", "MTR-90004"])
            self.assertEqual(rec["acknowledgedMotors"], ["MTR-90003", "MTR-90004"]); self.assertEqual(rec["registryProvenance"], lots.PROVENANCE)
            self.assertIn("not authentication", rec["acknowledgementNote"])
            app = Manufacturing(db)
            snap = app.snapshot(trusted_anchor=TrustedAnchor(Path(rec["accepted"]), c0)); app.close()
            self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertTrue(snap["eligibility"]["MTR-90003"]["currentReleaseEligible"]); self.assertFalse(snap["eligibility"]["MTR-90002"]["currentReleaseEligible"])

    def test_registry_change_between_propose_and_accept_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = self.setup(d, {"MTR-90003": (SAFE, "BR-312", False)})
            prop = checkpoint_ops.propose(db, c0, custody); cand = Path(prop["candidate"])
            with self.assertRaises(SystemExit) as cm:
                checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90003"], expected_registry_digest="0" * 64)
            self.assertIn("registry changed", str(cm.exception))
            rec = checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90003"], expected_registry_digest=prop["review"]["registry"]["digest"])
            self.assertEqual(rec["registryDigest"], prop["review"]["registry"]["digest"])

    def test_no_checkpoint_renewal_launders_ambiguity(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = self.setup(d, {"MTR-90001": ("UNKNOWN", SAFE, True)})
            prop = checkpoint_ops.propose(db, c0, custody)
            with self.assertRaises(SystemExit):
                checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], ["MTR-90001"])
            # even a hand-made successor anchor (outside the tool) leaves the read-side guard in force
            app = Manufacturing(db)
            snap = app.snapshot(trusted_anchor=TrustedAnchor(Path(prop["candidate"]), c0)); app.close()
            self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertFalse(snap["eligibility"]["MTR-90001"]["currentReleaseEligible"])


def tearDownModule():
    out = os.environ.get("LOT_AB_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
