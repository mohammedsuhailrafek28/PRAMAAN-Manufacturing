"""Adversarial and negative-reproduction tests for the lot-identity research candidates (disposable synthetic DBs, loopback only).
Run: python -B -m unittest research.lot_identity.test_lot_identity   (from the repository root)
Evidence is written to research/lot_identity/results/extra_evidence.json when LOT_EVIDENCE_OUT is set.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H  # noqa: E402
import lotid  # noqa: E402
from application import server as server_mod, checkpoint_ops  # noqa: E402
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.service import Manufacturing  # noqa: E402

EVIDENCE = {}


def put(key, value):
    EVIDENCE[key] = value


class Negative(unittest.TestCase):
    """The reproduced v1.0 defect, kept as a permanent negative test on the unmodified frozen code."""

    def test_v1_0_clears_unknown_and_near_miss_lots(self):
        for lot in ("UNKNOWN", "BR-2O4", "br-204", "BR-204​", "BR-999"):
            r = H.case(Manufacturing, "assemble", lot, "DE", "scoped DE")
            self.assertTrue(r["result"]["eligible"], lot)           # the defect: current eligibility from an unestablished identity
            self.assertEqual(r["result"]["action"], "RELEASE_ELIGIBLE")


class Candidates(unittest.TestCase):
    def test_bad_lots_never_clear_candidates(self):
        for cls in (H.StrategyA, H.StrategyB):
            for lot in ("UNKNOWN", "N/A", "", "   ", None, "BR-2O4", "br-204", "BR-204 ", "BR–204", "BR-204​", "BR-240"):
                for slot in ("DE", "NDE"):
                    for scope in ("scoped DE", "scoped NDE", "unspecified"):
                        r = H.case(cls, "assemble", lot, slot, scope)
                        self.assertFalse(r.get("result", {}).get("eligible", False), (cls.__name__, repr(lot), slot, scope))

    def test_registered_controls(self):
        for cls in (H.StrategyA, H.StrategyB):
            ok = H.case(cls, "assemble", "BR-310", "DE", "scoped DE")["result"]
            self.assertTrue(ok["eligible"], cls.__name__)
            bad = H.case(cls, "assemble", "BR-204", "DE", "scoped DE")["result"]
            self.assertFalse(bad["eligible"]); self.assertEqual(bad["finding"], "AFFECTED")

    def test_known_limit_of_B_unregistered_wellformed_lot(self):
        """B has no registry: a well-formed different string is still treated as unaffected. Asserted so the limit stays visible."""
        self.assertTrue(H.case(H.StrategyB, "assemble", "BR-999", "DE", "scoped DE")["result"]["eligible"])
        self.assertEqual(H.case(H.StrategyA, "assemble", "BR-999", "DE", "scoped DE")["capture"][:8], "REJECTED")
        for lot in ("BR-555", "BR-666"):   # not yet effective / withdrawn
            self.assertTrue(H.case(H.StrategyB, "assemble", lot, "DE", "scoped DE")["result"]["eligible"], lot)
            self.assertEqual(H.case(H.StrategyA, "assemble", lot, "DE", "scoped DE")["capture"][:8], "REJECTED", lot)

    def test_known_limit_of_A_events_not_through_the_service(self):
        """A validates only at capture. A database created by v1.0 (or any capture that bypasses the service) keeps its UNKNOWN lot."""
        with tempfile.TemporaryDirectory() as d:
            legacy = Manufacturing(Path(d) / "m.sqlite"); legacy.create_unit(H.MOTOR); legacy.assemble(H.MOTOR, "UNKNOWN", "BR-310"); legacy.ship(H.MOTOR); legacy.announce("BR-204", ["DE"]); legacy.close()
            res = {}
            for name, cls in (("BASELINE_V1_0", Manufacturing), ("A", H.StrategyA), ("B", H.StrategyB)):
                app = cls(Path(d) / "m.sqlite")
                try:
                    res[name] = H.summarize(H.current_snapshot(app, d))
                finally:
                    app.close()
                os.remove(Path(d) / "a.json")
            put("legacy_database_unknown_lot", res)
            self.assertTrue(res["BASELINE_V1_0"]["eligible"]); self.assertTrue(res["A"]["eligible"]); self.assertFalse(res["B"]["eligible"])


class Atomicity(unittest.TestCase):
    def crash_at(self, cls, op, k, lots):
        with tempfile.TemporaryDirectory() as d:
            app = cls(Path(d) / "m.sqlite"); app.create_unit(H.MOTOR)
            if op == "replace":
                app.assemble(H.MOTOR, "BR-204", "BR-310")
            before = len(app.events(H.MOTOR))
            real, n = app.ledger.capture, [0]

            def flaky(*a, **kw):
                if n[0] == k:
                    raise RuntimeError("injected crash")
                n[0] += 1
                return real(*a, **kw)
            app.ledger.capture = flaky
            try:
                (app.assemble(H.MOTOR, *lots) if op == "assemble" else app.replace(H.MOTOR, lots[0]))
                crashed = False
            except RuntimeError:
                crashed = True
            app.ledger.capture = real
            out = dict(op=op, lots=list(lots), crashAfterEvents=k, crashed=crashed, eventsWritten=len(app.events(H.MOTOR)) - before)
            try:
                (app.assemble(H.MOTOR, *lots) if op == "assemble" else app.replace(H.MOTOR, lots[0])); out["retry"] = "ACCEPTED"
            except Exception as e:
                out["retry"] = H.err(e)[:90]
            try:
                app.announce("BR-204", ["DE"])
                try:
                    if op == "assemble":
                        app.ship(H.MOTOR)  # shipping needs a closed build; rejected for a partial build
                except Exception as e:
                    out["shipAfterPartial"] = H.err(e)[:70]
                try:
                    out["afterRetry"] = H.summarize(H.current_snapshot(app, d))
                except Exception as e:
                    out["afterRetry"] = "SNAPSHOT_BLOCKED " + H.err(e)[:110]
            finally:
                app.close()
            return out

    def test_partial_writes_never_clear_a_recalled_lot(self):
        rows = []
        for op, lots, kmax in (("assemble", ("BR-204", "BR-310"), 8), ("assemble", ("BR-310", "BR-312"), 8), ("replace", ("BR-310",), 5)):
            for k in range(kmax):
                rows.append(self.crash_at(Manufacturing, op, k, lots))
        put("crash_injection_baseline", rows)
        for r in rows:
            after = r["afterRetry"]
            if isinstance(after, dict) and r["retry"] != "ACCEPTED":
                self.assertFalse(after["eligible"], r)     # an unfinished (partial) capture of a recalled-lot unit is never current-eligible

    def test_malformed_lot_leaves_no_residue_in_candidates(self):
        with tempfile.TemporaryDirectory() as d:
            for name, cls in (("BASELINE_V1_0", Manufacturing), ("A", H.StrategyA), ("B", H.StrategyB)):
                app = cls(Path(d) / (name + ".sqlite")); app.create_unit(H.MOTOR)
                try:
                    app.assemble(H.MOTOR, "   ", "BR-310")
                except Exception:
                    pass
                n = len(app.events(H.MOTOR))
                try:
                    app.assemble(H.MOTOR, "BR-310", "BR-312"); retry = "ACCEPTED"
                except Exception as e:
                    retry = H.err(e)
                put(f"whitespace_residue_{name}", dict(eventsLeft=n, retryAfterFailure=retry))
                if name == "BASELINE_V1_0":
                    self.assertGreater(n, 0)
                else:
                    self.assertEqual(n, 0); self.assertEqual(retry, "ACCEPTED")
                app.close()


class Provenance(unittest.TestCase):
    def test_supplier_scope(self):
        with tempfile.TemporaryDirectory() as d:
            out = {}
            for name, cls in (("BASELINE_V1_0", Manufacturing), ("A", H.StrategyA)):
                app = cls(Path(d) / (name + ".sqlite")); app.create_unit(H.MOTOR); app.assemble(H.MOTOR, "BR-401", "BR-310")
                out[name] = {e["payload"]["lot"]: e["payload"]["supplierId"] for e in app.events(H.MOTOR) if e["eventType"] == "BEARING_MANUFACTURED"}
                app.close()
            put("supplier_attribution", out)
            self.assertEqual(out["BASELINE_V1_0"]["BR-401"], "SUP-KAV-02")   # v1.0 hard-codes supplier by one lot name (registered supplier is NSB)
            self.assertEqual(out["A"]["BR-401"], "SUP-NSB-01")

    def test_conflicting_alias_and_scope(self):
        reg = lotid.conflicting_registry()
        self.assertEqual(reg.resolve("ALIAS-1").status, "ALIAS_CONFLICT")
        with tempfile.TemporaryDirectory() as d:
            app = H.StrategyA(Path(d) / "m.sqlite", registry=reg); app.create_unit(H.MOTOR)
            with self.assertRaises(Exception) as cm:
                app.assemble(H.MOTOR, "ALIAS-1", "BR-310")
            self.assertIn("ALIAS_CONFLICT", str(cm.exception)); self.assertEqual(len(app.events(H.MOTOR)), 0)
            app.close()
        self.assertEqual(lotid.demo_registry().resolve("NSB-204").canonical, "BR-204")   # declared alias resolves to the canonical recalled lot


class Api(unittest.TestCase):
    def serve(self, cls, d):
        db, anchor = Path(d) / "h.sqlite", Path(d) / "a.json"
        app = cls(db); app.create_unit(H.MOTOR); app.close()
        app = Manufacturing(db); publish_candidate(anchor, export_anchor(app)); app.close()
        server_mod.Manufacturing = cls
        srv = server_mod.make_server(db, 0, trusted_anchor=anchor)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, f"http://127.0.0.1:{srv.server_port}"

    def post(self, base, tok, path, body):
        req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": tok})
        try:
            with urlopen(req) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def test_api_cannot_inject_eligibility_or_bad_lots(self):
        res = {}
        try:
            for name, cls in (("BASELINE_V1_0", Manufacturing), ("A", H.StrategyA), ("B", H.StrategyB)):
                with tempfile.TemporaryDirectory() as d:
                    srv, base = self.serve(cls, d)
                    try:
                        tok = json.load(urlopen(base + "/api/session"))["token"]
                        extra = {"currentReleaseEligible": True, "eligibility": {H.MOTOR: {"currentReleaseEligible": True}}, "trusted": True}
                        s1, _ = self.post(base, tok, f"/api/units/{H.MOTOR}/assemble", {"deLot": "UNKNOWN", "ndeLot": "BR-310", **extra})
                        self.post(base, tok, f"/api/units/{H.MOTOR}/ship", {})
                        s2, _ = self.post(base, tok, "/api/recalls", {"lot": "BR-204", "affectedSlots": ["DE"]})
                        s3, _ = self.post(base, tok, "/api/recalls", {"lot": "N/A"})
                        snap = json.load(urlopen(base + "/api/snapshot"))
                        res[name] = dict(assembleUnknown=s1, recall=s2, recallSentinelAfterPolicy=s3, checkpoint=snap["checkpoint"]["state"],
                                         eligible=snap["eligibility"][H.MOTOR]["currentReleaseEligible"])
                        self.assertFalse(snap["eligibility"][H.MOTOR]["currentReleaseEligible"])   # no checkpoint renewal: never current
                    finally:
                        srv.shutdown(); srv.server_close()
        finally:
            server_mod.Manufacturing = Manufacturing
        put("api_injection", res)
        self.assertEqual(res["BASELINE_V1_0"]["assembleUnknown"], 200)
        self.assertEqual(res["A"]["assembleUnknown"], 400); self.assertEqual(res["B"]["assembleUnknown"], 400)

    def test_static_previews_carry_no_eligibility(self):
        root = HERE.parents[1] / "recall-ui" / "public" / "data"
        for f in root.glob("*.json"):
            self.assertNotIn('"currentReleaseEligible"', f.read_text(encoding="utf-8"), f.name)


class CheckpointRenewal(unittest.TestCase):
    def renew(self, db, current, custody):
        prop = checkpoint_ops.propose(db, current, custody)
        if prop["status"] != checkpoint_ops.STATUS_PROPOSED:
            return None
        return checkpoint_ops.accept(db, current, custody, prop["candidate"], "synthetic-custodian", prop["candidateSha256"])["accepted"]

    def test_renewal_does_not_launder_ambiguity(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); db, cur, custody = d / "r.sqlite", d / "c0.json", d / "custody"
            app = H.StrategyB(db); app.create_unit(H.MOTOR); app.close()
            app = Manufacturing(db); publish_candidate(cur, export_anchor(app)); app.close()
            # capture an unknown lot with the legacy (unmodified) writer to model data entered before the fix
            legacy = Manufacturing(db); legacy.assemble(H.MOTOR, "UNKNOWN", "BR-310"); legacy.ship(H.MOTOR); legacy.announce("BR-204", ["DE"]); legacy.close()
            accepted = self.renew(db, cur, custody)
            res = {}
            for name, cls in (("BASELINE_V1_0", Manufacturing), ("B", H.StrategyB)):
                app = cls(db)
                try:
                    from application.anchors import TrustedAnchor
                    snap = app.snapshot(trusted_anchor=TrustedAnchor(Path(accepted), cur))
                    res[name] = dict(checkpoint=snap["checkpoint"]["state"], eligible=snap["eligibility"][H.MOTOR]["currentReleaseEligible"],
                                     guard=snap.get("identityGuard", {}).get("motors", {}).get(H.MOTOR))
                finally:
                    app.close()
            put("checkpoint_renewal_after_ambiguity", res)
            self.assertEqual(res["BASELINE_V1_0"]["checkpoint"], "ANCHORED_CURRENT"); self.assertTrue(res["BASELINE_V1_0"]["eligible"])
            self.assertEqual(res["B"]["checkpoint"], "ANCHORED_CURRENT"); self.assertFalse(res["B"]["eligible"])


def tearDownModule():
    out = os.environ.get("LOT_EVIDENCE_OUT")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str))


if __name__ == "__main__":
    unittest.main()
