"""v1.1 safety hardening: registry custody (checkpoint-bound registry snapshots), NDE quarantine/recovery, unverified sightings, separate integrity guard.
Disposable synthetic DBs, loopback only. Run: python -B -m unittest application.test_v11_hardening -v
Set V11_EVIDENCE=<file> to write the adversarial results as JSON.
The binding is same-host: these tests prove unreviewed registry drift is detected and fails closed; they do not demonstrate independent custody.
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
from . import registry_binding as rb
from . import server as server_mod
from . import checkpoint_ops
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .service import Manufacturing, PART, ValidationFailure
from .test_lot_identity_ab import raw_assemble, entry, decision, summarize, M, RECALLED, SAFE

EVIDENCE = {}
LEGACY = "LEG-777"          # a legacy lot that the registry does not know


def base_doc():
    return json.loads(lots.DEFAULT_REGISTRY.read_text(encoding="utf-8"))


def mutated(fn):
    doc = base_doc(); fn(doc); return doc


def reg(doc):
    return lots.LotRegistry(doc)


def read_snapshot(db, anchor, doc=None, previous=None):
    app = Manufacturing(db, lot_registry=reg(doc) if doc is not None else None)
    try:
        return app.snapshot(trusted_anchor=TrustedAnchor(anchor, previous))
    finally:
        app.close()


def world(d, extra_unknown=False):
    """One legitimate motor (eligible under registry A), optionally a legacy motor on an unregistered lot. Checkpoint c0 is current and bound to registry A."""
    db, c0, custody = Path(d) / "w.sqlite", Path(d) / "c0.json", Path(d) / "custody"
    app = Manufacturing(db)
    app.create_unit(M); app.assemble(M, SAFE, "BR-312"); app.ship(M)
    if extra_unknown:
        app.create_unit("MTR-90002"); raw_assemble(app, "MTR-90002", LEGACY, SAFE); app.ship("MTR-90002")
    app.announce(RECALLED, ["DE"]); app.snapshot()
    publish_candidate(c0, export_anchor(app)); app.close()
    return db, c0, custody


class RegistryCustody(unittest.TestCase):
    def check_blocked(self, d, db, c0, doc, expect_changes, label):
        s = read_snapshot(db, c0, doc)
        rbk = s["lotIdentity"]["registryBinding"]
        res = dict(label=label, checkpoint=s["checkpoint"]["state"], bindingStatus=rbk["status"], changes=rbk["changes"],
                   eligible=s["eligibility"][M]["currentReleaseEligible"], action=decision(s)["operationalAction"],
                   evaluatorAction=decision(s)["evaluatorOperationalAction"], reasons=sorted({f["reason"] for f in decision(s)["identityGuard"]["findings"]}))
        EVIDENCE.setdefault("registryCustody", []).append(res)
        self.assertEqual(s["checkpoint"]["state"], "ANCHORED_CURRENT", res)            # the ledger checkpoint itself is fine (H1/H2 unchanged)
        self.assertEqual(rbk["status"], "DISCREPANCY", res)
        self.assertFalse(res["eligible"], res)
        self.assertEqual(res["action"], "RECALL_HOLD", res)
        self.assertEqual(res["evaluatorAction"], "RELEASE_ELIGIBLE", res)                # evaluator output is untouched; the guard is what holds
        self.assertIn("REGISTRY_BINDING_DISCREPANCY", res["reasons"], res)
        kinds = {(c["change"], c.get("field")) for c in rbk["changes"]}
        for k in expect_changes:
            self.assertIn(k, kinds, res)

    def test_unchanged_registry_is_eligible(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            s = read_snapshot(db, c0)
            self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "OK")
            self.assertTrue(s["eligibility"][M]["currentReleaseEligible"])

    def test_registry_modified_after_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            self.check_blocked(d, db, c0, mutated(lambda x: x["entries"][0].update(supplierName="Someone Else")), {("FIELD_CHANGED", "supplierName")}, "modified")

    def test_registry_rolled_back(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            self.check_blocked(d, db, c0, mutated(lambda x: x["entries"].pop()), {("ENTRY_REMOVED", None)}, "rolled back (entry removed)")
            self.check_blocked(d, db, c0, mutated(lambda x: x.update(version=x["version"] - 1)), {("DOCUMENT_FIELD_CHANGED", "version")}, "rolled back (version)")

    def test_unknown_legacy_lot_registered_retroactively(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d, extra_unknown=True)
            held = read_snapshot(db, c0)
            self.assertFalse(held["eligibility"]["MTR-90002"]["currentReleaseEligible"])        # unknown lot: held under registry A
            doc = mutated(lambda x: x["entries"].append(entry(LEGACY)))
            s = read_snapshot(db, c0, doc)
            for motor in (M, "MTR-90002"):                                                        # nothing becomes eligible under the OLD checkpoint, including the legitimate motor
                self.assertFalse(s["eligibility"][motor]["currentReleaseEligible"], motor)
            self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "DISCREPANCY")
            self.assertIn(("ENTRY_ADDED", LEGACY), {(c["change"], c["lot"]) for c in s["lotIdentity"]["registryBinding"]["changes"]})
            EVIDENCE["retroactiveRegistration"] = dict(underOldCheckpoint={m: s["eligibility"][m] for m in s["eligibility"]})

    def test_alias_redirect_supplier_change_and_effective_dates(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            def redirect(x):
                for e in x["entries"]:
                    if "NSB-204" in e.get("aliases", []):
                        e["aliases"].remove("NSB-204")
                    if e["canonical"] == "BR-312":
                        e["aliases"] = e.get("aliases", []) + ["NSB-204"]
            self.check_blocked(d, db, c0, mutated(redirect), {("ALIAS_REDIRECTED", None)}, "alias redirected")
            self.check_blocked(d, db, c0, mutated(lambda x: next(e for e in x["entries"] if e["canonical"] == "BR-310").update(supplierId="SUP-NSB-01")), {("FIELD_CHANGED", "supplierId")}, "supplier changed")
            self.check_blocked(d, db, c0, mutated(lambda x: next(e for e in x["entries"] if e["canonical"] == "BR-310").update(effectiveFrom="2030-01-01T00:00:00Z")), {("FIELD_CHANGED", "effectiveFrom")}, "effective date moved")
            self.check_blocked(d, db, c0, mutated(lambda x: next(e for e in x["entries"] if e["canonical"] == "BR-310").update(status="WITHDRAWN")), {("FIELD_CHANGED", "status")}, "withdrawn")

    def test_missing_invalid_and_foreign_bindings_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            side = rb.binding_path(c0); good = side.read_bytes()
            for label, writer, want in (("missing", lambda: side.unlink(), "MISSING"), ("garbage", lambda: side.write_bytes(b"{not json"), "INVALID"),
                                        ("digest-mismatch", lambda: side.write_text(json.dumps(dict(json.loads(good), registryDigest="0" * 64))), "INVALID"),
                                        ("other-checkpoint", lambda: side.write_text(json.dumps(dict(json.loads(good), checkpointSha256="1" * 64))), "INVALID"),
                                        ("provenance-forged", lambda: side.write_text(json.dumps(dict(json.loads(good), registryDocument=dict(json.loads(good)["registryDocument"], provenance="REAL_SUPPLIER_ATTESTED")))), "INVALID")):
                side.write_bytes(good) if label != "missing" else None
                if label == "missing" and not side.exists():
                    side.write_bytes(good)
                writer()
                s = read_snapshot(db, c0)
                st = s["lotIdentity"]["registryBinding"]["status"]
                EVIDENCE.setdefault("bindingTamper", []).append(dict(label=label, status=st, eligible=s["eligibility"][M]["currentReleaseEligible"]))
                self.assertEqual(st, want, label); self.assertFalse(s["eligibility"][M]["currentReleaseEligible"], label)
                side.write_bytes(good)

    def test_valid_update_review_and_new_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d, extra_unknown=True)
            doc = mutated(lambda x: x["entries"].append(entry(LEGACY)))
            import application.service as S
            regfile = Path(d) / "registry.v2.json"; regfile.write_text(json.dumps(doc), encoding="utf-8")
            S.DEFAULT_LOT_REGISTRY = regfile
            try:
                prop = checkpoint_ops.propose(db, c0, custody)
                self.assertEqual(prop["status"], checkpoint_ops.STATUS_PROPOSED, prop)             # ledger unchanged, but the registry changed: a renewal is needed
                rv = prop["review"]
                self.assertTrue(rv["registryChange"]["requiresAcknowledgement"])
                self.assertIn(("ENTRY_ADDED", LEGACY), {(c["change"], c["lot"]) for c in rv["registryChange"]["changes"]})
                by = {r["motor"]: r for r in rv["rows"]}
                self.assertTrue(by["MTR-90002"]["identityResolvedByRegistryChange"])
                self.assertIn("MTR-90002", rv["requiresAcknowledgement"])                           # eligibility created by a registry edit needs the same explicit motor acknowledgement
                cand = Path(prop["candidate"])
                with self.assertRaises(SystemExit) as cm:                                           # no registry acknowledgement -> refused
                    checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90002"])
                self.assertIn("registry differs", str(cm.exception))
                with self.assertRaises(SystemExit):                                                 # wrong registry digest -> refused
                    checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90002"], acknowledge_registry="0" * 64)
                with self.assertRaises(SystemExit) as cm:                                           # registry ack without the motor ack -> refused
                    checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], [], acknowledge_registry=rv["registry"]["digest"])
                self.assertIn("acknowledged individually", str(cm.exception))
                self.assertFalse((custody / "accepted").exists())
                rec = checkpoint_ops.accept(db, c0, custody, cand, "synthetic", prop["candidateSha256"], ["MTR-90002"], acknowledge_registry=rv["registry"]["digest"])
                acc = Path(rec["accepted"])
                self.assertTrue(rb.binding_path(acc).exists()); self.assertTrue(rec["registryChangeAcknowledged"])
                s = read_snapshot(db, acc, doc, c0)
                self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "OK")
                self.assertTrue(s["eligibility"]["MTR-90002"]["currentReleaseEligible"]); self.assertTrue(s["eligibility"][M]["currentReleaseEligible"])
                # replay: the OLD checkpoint read with the NEW registry, and the NEW checkpoint read with the OLD registry, both fail closed
                old_new = read_snapshot(db, c0, doc)
                new_old = read_snapshot(db, acc, base_doc(), c0)
                for label, snap in (("old checkpoint + new registry", old_new), ("new checkpoint + old registry", new_old)):
                    self.assertEqual(snap["lotIdentity"]["registryBinding"]["status"], "DISCREPANCY", label)
                    self.assertFalse(snap["eligibility"][M]["currentReleaseEligible"], label)
                    EVIDENCE.setdefault("replay", []).append(dict(label=label, status=snap["lotIdentity"]["registryBinding"]["status"]))
                # a second proposal is not needed once both ledger and registry are bound
                self.assertEqual(checkpoint_ops.propose(db, acc, custody, c0)["status"], "NO_CANDIDATE_NEEDED")
            finally:
                S.DEFAULT_LOT_REGISTRY = None

    def test_checkpoint_without_prior_binding_requires_registry_acknowledgement(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            rb.binding_path(c0).unlink()                                                             # a checkpoint from before this feature
            self.assertEqual(read_snapshot(db, c0)["lotIdentity"]["registryBinding"]["status"], "MISSING")
            app = Manufacturing(db); app.create_unit("MTR-90009"); app.assemble("MTR-90009", SAFE, "BR-312"); app.ship("MTR-90009"); app.close()   # ledger advances
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["registryChange"]["priorBinding"], "MISSING_OR_UNREADABLE")
            with self.assertRaises(SystemExit):
                checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], ["MTR-90009"])
            rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], ["MTR-90009"], acknowledge_registry=prop["review"]["registry"]["digest"])
            self.assertTrue(rb.binding_path(Path(rec["accepted"])).exists())


class UnverifiedSightings(unittest.TestCase):
    def fresh(self, d, recall_slots=("DE",)):
        app = Manufacturing(Path(d) / "s.sqlite")
        app.create_unit(M); app.assemble(M, SAFE, "BR-312"); app.ship(M); app.announce(RECALLED, list(recall_slots))
        return app

    def anchored(self, app, d, tag):
        a = Path(d) / f"a-{tag}.json"
        app.snapshot(); publish_candidate(a, export_anchor(app))
        return app.snapshot(trusted_anchor=TrustedAnchor(a))

    def test_sighting_preserved_raw_never_clears_and_does_not_touch_the_evaluator(self):
        with tempfile.TemporaryDirectory() as d:
            app = self.fresh(d)
            try:
                clean = self.anchored(app, d, "clean")
                c0 = decision(clean)
                registry_digest, events_before = app.registry.digest, len(app.events(M))
                app.observe(M, "ZZ-9 (scratched)", "NDE")
                ev = [e for e in app.events(M) if e["eventType"] == "SLOT_STATE_VERIFIED"][-1]
                self.assertEqual(ev["payload"]["observedLot"], "ZZ-9 (scratched)")                  # raw identity preserved verbatim
                self.assertEqual((ev["payload"]["provisional"], ev["payload"]["method"], ev["sourceId"], ev["payload"]["slot"]), (True, "HANDHELD_LABEL_READ", ev["sourceId"], "NDE"))
                self.assertTrue(ev["occurredAt"] and ev["sourceId"])
                s = self.anchored(app, d, "sighted")
                c1 = decision(s)
                for k in ("evidenceFinding", "reasonCodes", "evaluatorOperationalAction"):          # evaluator isolation: untrusted claim changes nothing the evaluator says
                    self.assertEqual(c1[k], c0[k], k)
                self.assertEqual(c0["operationalAction"], "RELEASE_ELIGIBLE"); self.assertEqual(c1["operationalAction"], "RECALL_HOLD")
                self.assertFalse(s["eligibility"][M]["currentReleaseEligible"])
                f = [x for x in c1["identityGuard"]["findings"] if x["source"] == "OBSERVATION"]
                self.assertEqual(f[0]["lot"], "ZZ-9 (scratched)"); self.assertEqual(f[0]["reason"], "UNREGISTERED")
                self.assertEqual(c1["quarantine"]["status"], "QUARANTINED_NOT_CLEARED"); self.assertEqual(c1["quarantine"]["clearance"], "NEVER_IMPLIED")
                self.assertEqual(app.registry.digest, registry_digest)                               # no registry entry
                self.assertEqual(len(s["components"]), len(clean["components"]))                      # no component
                self.assertEqual({l["lotId"] for l in s["lots"]}, {l["lotId"] for l in clean["lots"]})  # no lot
                self.assertEqual(len([e for e in app.events(M)]) - events_before, 1)
                EVIDENCE["sighting"] = dict(rawPreserved=ev["payload"]["observedLot"], action=c1["operationalAction"], evaluatorUnchanged=True)
            finally:
                app.close()

    def test_sighting_naming_recalled_lot_or_sentinel_cannot_exclude_or_clear(self):
        with tempfile.TemporaryDirectory() as d:
            app = self.fresh(d)
            try:
                for lot in (RECALLED, "UNKNOWN", "N/A"):
                    app.observe(M, lot, "DE")
                s = self.anchored(app, d, "x")
                self.assertFalse(s["eligibility"][M]["currentReleaseEligible"])
                self.assertNotEqual(decision(s)["operationalAction"], "RELEASE_ELIGIBLE")
            finally:
                app.close()

    def test_invalid_sightings_are_refused_without_events(self):
        with tempfile.TemporaryDirectory() as d:
            app = self.fresh(d)
            try:
                n = len(app.events(M))
                for bad in (None, "", "   ", "x" * 81, "a\x00b", 12, ["BR-204"]):
                    with self.assertRaises(ValidationFailure, msg=repr(bad)):
                        app.observe(M, bad, "DE")
                with self.assertRaises(ValidationFailure):
                    app.observe(M, "BR-310", "MID")
                self.assertEqual(len(app.events(M)), n)
            finally:
                app.close()

    def test_registered_sighting_is_not_held_and_later_install_supersedes_an_unverified_one(self):
        with tempfile.TemporaryDirectory() as d:
            app = self.fresh(d)
            try:
                app.observe(M, "BR-205", "DE")                                                       # registered, unaffected -> not held
                self.assertTrue(self.anchored(app, d, "reg")["eligibility"][M]["currentReleaseEligible"])
                app.observe(M, "ZZ-9", "NDE")
                self.assertFalse(self.anchored(app, d, "unreg")["eligibility"][M]["currentReleaseEligible"])
                app.replace(M, "BR-311", "NDE")                                                       # NDE physically re-installed with a registered lot
                s = self.anchored(app, d, "after")
                self.assertTrue(s["eligibility"][M]["currentReleaseEligible"], decision(s)["identityGuard"])
                self.assertTrue(any(e["payload"].get("observedLot") == "ZZ-9" for e in app.events(M)))   # the sighting itself is still in the ledger
            finally:
                app.close()

    def test_historical_basis_keeps_every_sighting(self):
        doc = lots.policy_findings  # the historical basis is policy-driven; exercised via lot_identity directly
        reg_ = lots.LotRegistry(base_doc())
        ev = lambda i, t, at, **p: dict(eventId=i, eventType=t, occurredAt=at, payload=p, supersedesEventId=None, workOrderId=None, sourceId="s")
        events = [ev("i1", "COMPONENT_INSTALLED", "2026-10-01T00:00:00Z", slot="NDE", lot="BR-310", manufacturingEventId=None),
                  ev("o1", "SLOT_STATE_VERIFIED", "2026-10-02T00:00:00Z", slot="NDE", observedLot="ZZ-9"),
                  ev("i2", "COMPONENT_INSTALLED", "2026-10-03T00:00:00Z", slot="NDE", lot="BR-310", manufacturingEventId=None)]
        cur = [f for f in lots.motor_findings(reg_, events, dict(exposureBasis="CURRENT_INSTALLATION"), PART) if f["source"] == "OBSERVATION"]
        his = [f for f in lots.motor_findings(reg_, events, dict(exposureBasis="HISTORICAL_OPERATION"), PART) if f["source"] == "OBSERVATION"]
        self.assertEqual((len(cur), len(his)), (0, 1))


class NdeRecovery(unittest.TestCase):
    def test_unknown_nde_is_quarantined_then_recovered_by_controlled_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = Path(d) / "n.sqlite", Path(d) / "c0.json", Path(d) / "custody"
            app = Manufacturing(db); app.create_unit(M); app.close()
            app = Manufacturing(db); publish_candidate(c0, export_anchor(app)); app.close()
            app = Manufacturing(db); raw_assemble(app, M, SAFE, "UNKNOWN"); app.ship(M); app.announce(RECALLED, ["DE"]); app.close()
            app = Manufacturing(db)
            try:
                before_events = copy.deepcopy(app.events(M))
                q = decision(read_snapshot(db, c0))                                                    # not yet checkpoint-current: still historical/ineligible
                self.assertEqual(q["identityGuard"]["status"], "IDENTITY_NOT_ESTABLISHED")
                self.assertEqual(q["quarantine"]["status"], "QUARANTINED_NOT_CLEARED"); self.assertEqual(q["quarantine"]["clearance"], "NEVER_IMPLIED")
                self.assertEqual(q["quarantine"]["steps"][0]["option"], "CONTROLLED_REPLACEMENT"); self.assertEqual(q["quarantine"]["steps"][0]["slot"], "NDE")
                with self.assertRaises(ValidationFailure):
                    app.replace(M, "UNKNOWN", "NDE")                                                    # no invented identity
                with self.assertRaises(ValidationFailure):
                    app.replace(M, "BR-999", "NDE")
                self.assertEqual(len(app.events(M)), len(before_events))
                app.replace(M, "BR-312", "NDE")
                after = app.events(M)
                self.assertEqual(after[:len(before_events)], before_events)                              # original evidence preserved, append only
                types = [e["eventType"] for e in after[len(before_events):]]
                self.assertEqual(types[0], "WORK_ORDER_OPENED"); self.assertEqual(types[-1], "WORK_ORDER_CLOSED")
                removed = next(e for e in after if e["eventType"] == "COMPONENT_REMOVED"); self.assertEqual(removed["payload"]["observedLot"], "UNKNOWN")
            finally:
                app.close()
            s = read_snapshot(db, c0)
            self.assertFalse(s["eligibility"][M]["currentReleaseEligible"])                              # no clearance before the checkpoint is renewed
            prop = checkpoint_ops.propose(db, c0, custody)
            row = next(r for r in prop["review"]["rows"] if r["motor"] == M)
            self.assertEqual(row["identityFindings"], [])
            self.assertIn(M, prop["review"]["requiresAcknowledgement"])
            with self.assertRaises(SystemExit):
                checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [])
            rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [M])
            s = read_snapshot(db, Path(rec["accepted"]), None, c0)
            self.assertEqual(s["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertTrue(s["eligibility"][M]["currentReleaseEligible"])
            self.assertIsNone(decision(s)["quarantine"])
            hist = next(iter(s["decisions"][M].values()))["history"]
            self.assertTrue(any(h["operationalAction"] == "RELEASE_ELIGIBLE" for h in hist) or hist)   # historical decisions retained
            EVIDENCE["ndeRecovery"] = dict(eventsPreserved=True, eligibleAfterRenewal=True, ineligibleBeforeRenewal=True)

    def test_unknown_nde_still_blocks_when_replacement_is_in_the_wrong_slot(self):
        with tempfile.TemporaryDirectory() as d:
            app = Manufacturing(Path(d) / "n.sqlite"); app.create_unit(M); raw_assemble(app, M, SAFE, "UNKNOWN"); app.ship(M); app.announce(RECALLED, ["DE"])
            try:
                app.replace(M, "BR-312", "DE")
                a = Path(d) / "a.json"; app.snapshot(); publish_candidate(a, export_anchor(app))
                s = app.snapshot(trusted_anchor=TrustedAnchor(a))
                self.assertFalse(s["eligibility"][M]["currentReleaseEligible"])
                self.assertEqual({f["slot"] for f in decision(s)["identityGuard"]["findings"]}, {"NDE"})
            finally:
                app.close()


class IntegrityGuard(unittest.TestCase):
    def test_interrupted_operation_has_its_own_guard_reason_and_api_surface(self):
        with tempfile.TemporaryDirectory() as d:
            db, anchor = Path(d) / "i.sqlite", Path(d) / "a.json"
            app = Manufacturing(db); app.create_unit(M)
            real, n = app.ledger.capture, [0]
            def flaky(*a, **kw):
                if n[0] == 3:
                    raise RuntimeError("injected crash")
                n[0] += 1
                return real(*a, **kw)
            app.ledger.capture = flaky
            try:
                app.assemble(M, SAFE, "BR-312")
            except RuntimeError:
                pass
            app.ledger.capture = real
            app.announce(RECALLED, ["DE"]); app.snapshot(); publish_candidate(anchor, export_anchor(app)); app.close()
            srv = server_mod.make_server(db, 0, trusted_anchor=anchor)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                snap = json.load(urlopen(f"http://127.0.0.1:{srv.server_port}/api/snapshot"))
            finally:
                srv.shutdown(); srv.server_close()
            c = decision(snap)
            self.assertEqual(c["integrityGuard"]["status"], "OPERATION_INTERRUPTED")
            self.assertEqual([f["reason"] for f in c["integrityGuard"]["findings"]], ["OPERATION_INTERRUPTED"])
            self.assertEqual(c["identityGuard"]["status"], "IDENTITY_ESTABLISHED_LOCAL_REGISTRY")         # identity is not blamed
            self.assertEqual(snap["operationalIntegrity"]["motors"][M][0]["reason"], "OPERATION_INTERRUPTED")
            self.assertFalse(snap["eligibility"][M]["currentReleaseEligible"])
            self.assertEqual(c["quarantine"]["steps"][0]["option"], "MANUAL_RECONCILIATION")
            app = Manufacturing(db)
            try:
                n0 = len(app.events(M))
                for call in (lambda: app.replace(M, "BR-310", "DE"), lambda: app.observe(M, "BR-310", "DE"), lambda: app.assemble(M, SAFE, "BR-312")):
                    with self.assertRaises(ValidationFailure):
                        call()
                self.assertEqual(len(app.events(M)), n0)                                                  # conservative: retry refused, nothing written
            finally:
                app.close()


class HttpSlotParameter(unittest.TestCase):
    def test_replace_and_observe_accept_slot_over_http_and_ignore_forged_fields(self):
        with tempfile.TemporaryDirectory() as d:
            db, anchor = Path(d) / "h.sqlite", Path(d) / "a.json"
            app = Manufacturing(db); app.create_unit(M); raw_assemble(app, M, SAFE, "UNKNOWN"); app.ship(M); app.announce(RECALLED, ["DE"])
            app.snapshot(); publish_candidate(anchor, export_anchor(app)); app.close()
            srv = server_mod.make_server(db, 0, trusted_anchor=anchor)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_port}"
            def post(path, body):
                tok = json.load(urlopen(base + "/api/session"))["token"]
                req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": tok})
                try:
                    with urlopen(req) as r:
                        return r.status, json.load(r)
                except HTTPError as e:
                    return e.code, json.load(e)
            try:
                self.assertEqual(post(f"/api/units/{M}/replace", {"lot": "BR-312", "slot": "MID"})[0], 400)
                self.assertEqual(post(f"/api/units/{M}/replace", {"lot": "UNKNOWN", "slot": "NDE"})[0], 400)
                self.assertEqual(post(f"/api/units/{M}/observe", {"lot": "", "slot": "NDE"})[0], 400)
                s, body = post(f"/api/units/{M}/observe", {"lot": "BR-2O4", "slot": "NDE", "currentReleaseEligible": True})
                self.assertEqual(s, 200)
                c = decision(body["snapshot"])
                self.assertEqual(c["operationalAction"], "RECALL_HOLD"); self.assertIn("OBSERVATION", {f["source"] for f in c["identityGuard"]["findings"]})
                s, body = post(f"/api/units/{M}/replace", {"lot": "BR-312", "slot": "NDE"})
                self.assertEqual(s, 200)
                self.assertFalse(body["snapshot"]["eligibility"][M]["currentReleaseEligible"])      # checkpoint not renewed: no clearance from the command alone
            finally:
                srv.shutdown(); srv.server_close()


def tearDownModule():
    out = os.environ.get("V11_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
