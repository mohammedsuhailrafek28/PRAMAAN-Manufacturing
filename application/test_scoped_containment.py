"""Scoped containment of an unverified sighting at checkpoint acceptance (research; owner decision 3 on FORMAT_V3). Disposable synthetic DBs, loopback only.
Run: python -B -m unittest application.test_scoped_containment -v     Set SCOPED_EVIDENCE=<file> to write the measured results as JSON.

Safe isolation: the sighted motor stays held and unrelated motors may be renewed. Mandatory global refusal: whenever a dependency cannot be ruled out, the whole
candidate is refused exactly as before. Same-host: this does not demonstrate independent custody or verification of any bearing.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from . import checkpoint_ops
from . import checkpoint_review as review_mod
from .anchors import export_anchor, publish_candidate
from .service import Manufacturing
from .test_lot_identity_ab import raw_assemble, decision, RECALLED, SAFE
from .test_v11_hardening import read_snapshot, base_doc, mutated, entry

A, B, S, T = "MTR-91001", "MTR-91002", "MTR-91003", "MTR-91004"
EVIDENCE = {}
SYNTH = "synthetic reviewer"


def load(path):
    return json.loads(Path(path).read_bytes())


def world(d):
    """A, B legitimate unaffected motors, S a further legitimate motor that will receive a sighting. Checkpoint c0 is a current V3 checkpoint."""
    db, c0, custody = Path(d) / "w.sqlite", Path(d) / "c0.json", Path(d) / "custody"
    app = Manufacturing(db)
    for m, de in ((A, SAFE), (B, SAFE), (S, SAFE)):
        app.create_unit(m); app.assemble(m, de, "BR-312"); app.ship(m)
    app.announce(RECALLED, ["DE"]); app.snapshot()
    publish_candidate(c0, export_anchor(app)); app.close()
    return db, c0, custody


def edit(db, fn):
    app = Manufacturing(db)
    try:
        fn(app); app.snapshot()
    finally:
        app.close()


def row(prop, motor):
    return next(r for r in prop["review"]["rows"] if r["motor"] == motor)


def unmet(r):
    return sorted(o["obligation"] for o in r["containment"]["obligations"] if not o["holds"])


def accept(db, current, custody, prop, acks=None, **kw):
    return checkpoint_ops.accept(db, current, custody, Path(prop["candidate"]), SYNTH, prop["candidateSha256"],
                                 prop["review"]["requiresAcknowledgement"] if acks is None else acks,
                                 acknowledge_registry=prop["review"]["registry"]["digest"] if prop["review"]["registryChange"]["requiresAcknowledgement"] else None, **kw)


class SafeIsolation(unittest.TestCase):
    def test_sighted_motor_stays_held_while_unrelated_motors_are_renewed(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "ZZ-9"))
            stale = read_snapshot(db, c0)
            self.assertEqual(stale["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
            self.assertTrue(all(not v["currentReleaseEligible"] for v in stale["eligibility"].values()))       # stale: nothing is current for anyone
            edit(db, lambda a: (a.create_unit(T), a.assemble(T, SAFE, "BR-312"), a.ship(T)))                      # unrelated work continues
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["refusedForIdentity"], [])
            self.assertEqual(prop["review"]["containedMotors"], [S])
            r = row(prop, S)
            self.assertTrue(r["identityUnsafeExclusion"] and r["containment"]["contained"], r)               # the row is NOT suppressed: it is still flagged, with its proof obligations
            self.assertEqual(unmet(r), [])
            self.assertEqual(r["guardedAction"], "RECALL_HOLD"); self.assertEqual(r["evaluatorAction"], "RELEASE_ELIGIBLE")
            with self.assertRaises(SystemExit) as cm:                                                         # the contained motor needs its own acknowledgement
                accept(db, c0, custody, prop, acks=[T])
            self.assertIn(S, str(cm.exception)); self.assertFalse((custody / "accepted").exists())
            rec = accept(db, c0, custody, prop)
            self.assertEqual(rec["containedMotors"], [S])
            s = read_snapshot(db, rec["accepted"], None, c0)
            self.assertEqual(s["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertEqual({m: v["currentReleaseEligible"] for m, v in s["eligibility"].items()}, {A: True, B: True, S: False, T: True})
            c = decision(s, S)
            self.assertEqual(c["operationalAction"], "RECALL_HOLD"); self.assertEqual(c["evaluatorOperationalAction"], "RELEASE_ELIGIBLE")
            self.assertEqual(c["quarantine"]["clearance"], "NEVER_IMPLIED")
            self.assertIn("OBSERVATION", {f["source"] for f in c["identityGuard"]["findings"]})
            EVIDENCE["safeIsolation"] = dict(eligibility=s["eligibility"], contained=rec["containedMotors"], obligations=r["containment"]["obligations"])

    def test_two_independent_unshared_sightings_are_both_contained(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: (a.observe(S, "ZZ-9"), a.observe(B, "QX-77")))
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["containedMotors"], [B, S]); self.assertEqual(prop["review"]["refusedForIdentity"], [])
            rec = accept(db, c0, custody, prop)
            s = read_snapshot(db, rec["accepted"], None, c0)
            self.assertEqual({m: v["currentReleaseEligible"] for m, v in s["eligibility"].items()}, {A: True, B: False, S: False})

    def test_a_contained_motor_stays_held_across_later_cycles_and_old_checkpoints(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "ZZ-9"))
            prop = checkpoint_ops.propose(db, c0, custody); rec = accept(db, c0, custody, prop)
            c1 = Path(rec["accepted"])
            edit(db, lambda a: (a.create_unit(T), a.assemble(T, SAFE, "BR-312"), a.ship(T)))
            prop2 = checkpoint_ops.propose(db, c1, custody, c0)                                                    # second cycle: still contained, still held
            self.assertEqual(prop2["review"]["containedMotors"], [S])
            rec2 = accept(db, c1, custody, prop2)
            for path, prev in ((c0, None), (c1, c0), (rec2["accepted"], c1)):                                 # no checkpoint in the chain makes S eligible
                s = read_snapshot(db, path, None, prev)
                self.assertFalse(s["eligibility"][S]["currentReleaseEligible"], str(path))
            self.assertTrue(read_snapshot(db, rec2["accepted"], None, c1)["eligibility"][T]["currentReleaseEligible"])

    def test_format_migration_does_not_release_a_contained_motor(self):
        with tempfile.TemporaryDirectory() as d:
            db, v2, custody = Path(d) / "w.sqlite", Path(d) / "v2.json", Path(d) / "custody"
            app = Manufacturing(db)
            for m in (A, B, S):
                app.create_unit(m); app.assemble(m, SAFE, "BR-312"); app.ship(m)
            app.announce(RECALLED, ["DE"]); app.snapshot()
            publish_candidate(v2, export_anchor(app, version=2)); app.close()                                  # legacy V2 root: never grants current eligibility
            edit(db, lambda a: a.observe(S, "ZZ-9"))
            held = read_snapshot(db, v2)
            self.assertTrue(all(not v["currentReleaseEligible"] for v in held["eligibility"].values()))
            prop = checkpoint_ops.propose(db, v2, custody)
            self.assertEqual(prop["review"]["containedMotors"], [S]); self.assertEqual(prop["review"]["refusedForIdentity"], [])
            rec = accept(db, v2, custody, prop)
            s = read_snapshot(db, rec["accepted"], None, v2)
            self.assertEqual(load(rec["accepted"])["body"]["format"], "PRAMAAN_A31_ANCHOR_V3")
            self.assertEqual({m: v["currentReleaseEligible"] for m, v in s["eligibility"].items()}, {A: True, B: True, S: False})
            EVIDENCE["formatMigrationContained"] = dict(v2="all held", v3={m: v["currentReleaseEligible"] for m, v in s["eligibility"].items()})

    def test_sighting_on_an_affected_motor_needs_no_containment(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            def go(a):
                a.create_unit(T); a.assemble(T, RECALLED, "BR-312"); a.ship(T); a.observe(T, "ZZ-9")
            edit(db, go)
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["refusedForIdentity"], []); self.assertEqual(prop["review"]["containedMotors"], [])
            rec = accept(db, c0, custody, prop)
            self.assertFalse(read_snapshot(db, rec["accepted"], None, c0)["eligibility"][T]["currentReleaseEligible"])


class MandatoryGlobalRefusal(unittest.TestCase):
    def refused(self, d, db, c0, custody, expect_unmet, expect_refused):
        prop = checkpoint_ops.propose(db, c0, custody)
        self.assertEqual(sorted(prop["review"]["refusedForIdentity"]), sorted(expect_refused), prop["review"]["refusedForIdentity"])
        for motor, names in expect_unmet.items():
            for n in names:
                self.assertIn(n, unmet(row(prop, motor)), (motor, unmet(row(prop, motor))))
        with self.assertRaises(SystemExit) as cm:
            accept(db, c0, custody, prop, acks=sorted({r["motor"] for r in prop["review"]["rows"]}))              # every acknowledgement supplied
        self.assertIn("isolation", str(cm.exception)); self.assertFalse((custody / "accepted").exists())
        return prop

    def test_same_string_on_two_motors_refuses_everything(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: (a.observe(S, "ZZ-9"), a.observe(B, "zz 9")))                                   # same string after normalisation
            self.refused(d, db, c0, custody, {S: ["STRING_NOT_SHARED_WITH_ANOTHER_MOTOR"], B: ["STRING_NOT_SHARED_WITH_ANOTHER_MOTOR"]}, [B, S])
            EVIDENCE["refusal_sharedString"] = "REFUSED"

    def test_lookalike_of_a_lot_in_use_elsewhere_refuses_everything(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "BR-31O"))                                                         # letter O for zero: resembles registered BR-310 installed on A, B
            self.refused(d, db, c0, custody, {S: ["NO_LOOKALIKE_OF_A_LOT_IN_USE_ELSEWHERE"]}, [S])
            EVIDENCE["refusal_lookalike"] = "REFUSED"

    def test_a_non_sighting_identity_finding_anywhere_refuses_everything(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            def go(a):
                a.observe(S, "ZZ-9"); a.create_unit(T); raw_assemble(a, T, "UNKNOWN", SAFE); a.ship(T)         # bypassed capture on another motor: INSTALL finding
            edit(db, go)
            prop = self.refused(d, db, c0, custody, {}, [T])
            self.assertEqual(prop["review"]["containedMotors"], [S])          # S itself is still isolable, but the candidate as a whole is refused because T is not
            EVIDENCE["refusal_otherMotorUnsafe"] = "REFUSED"

    def test_sighting_mixed_with_an_install_finding_on_the_same_motor_is_not_contained(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            def go(a):
                a.create_unit(T); raw_assemble(a, T, "UNKNOWN", SAFE); a.ship(T); a.observe(T, "ZZ-9")
            edit(db, go)
            self.refused(d, db, c0, custody, {T: ["ONLY_SIGHTING_FINDINGS"]}, [T])

    def test_sighting_of_a_withdrawn_or_conflicting_lot_is_a_registry_matter_not_a_motor_matter(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "BR-420"))                                                         # a registry-withdrawn lot
            self.refused(d, db, c0, custody, {S: ["ONLY_UNESTABLISHED_STRINGS"]}, [S])

    def test_interrupted_operation_elsewhere_is_its_own_per_motor_hold_and_does_not_widen_or_narrow_containment(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            def go(a):
                a.observe(S, "ZZ-9")
                a.event(B, "WORK_ORDER_OPENED", "MES", dict(orderType="REWORK", expectedChanges=[dict(slot="DE", action="REPLACE")]), work_order="RW-OPEN")
            edit(db, go)
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["containedMotors"], [S]); self.assertEqual(prop["review"]["refusedForIdentity"], [])
            rec = accept(db, c0, custody, prop)
            s = read_snapshot(db, rec["accepted"], None, c0)
            self.assertEqual({m: v["currentReleaseEligible"] for m, v in s["eligibility"].items()}, {A: True, B: False, S: False})

    def test_registry_mutation_refuses_and_never_reaches_containment(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "ZZ-9"))
            prop = checkpoint_ops.propose(db, c0, custody)
            self.assertEqual(prop["review"]["containedMotors"], [S])
            doc = mutated(lambda x: x["entries"].append(entry("ZZ-9")))                                        # the registry changes between propose and accept
            app = Manufacturing(db, lot_registry=review_mod.lots.LotRegistry(doc))
            try:
                bad = review_mod.build_review(app, load(c0)["body"], load(prop["candidate"])["body"], c0, None)   # no verified candidate binding at all
            finally:
                app.close()
            self.assertEqual(bad["containedMotors"], []); self.assertIn("REGISTRY_BINDING_OK", unmet(bad["rows"][0]))
            self.assertEqual(review_mod.containment(S, [dict(source="OBSERVATION", reason="UNREGISTERED", lot="ZZ-9", resembles=[])], [], [], False, {S: {"ZZ-9"}}, "RECALL_HOLD")[0], False)
            with self.assertRaises(SystemExit):                                                                # the app now verifies against a different registry: accept refuses on binding
                saved = checkpoint_ops.Manufacturing
                checkpoint_ops.Manufacturing = lambda database: saved(database, lot_registry=review_mod.lots.LotRegistry(doc))
                try:
                    accept(db, c0, custody, prop)
                finally:
                    checkpoint_ops.Manufacturing = saved
            self.assertFalse((custody / "accepted").exists())

    def test_the_proof_obligations_are_individually_necessary(self):
        ok = dict(found=[dict(source="OBSERVATION", reason="UNREGISTERED", lot="ZZ-9", resembles=[])], broken=[], base=[], binding_ok=True,
                  strings={S: {"ZZ-9"}, A: {"BR-310"}}, action="RECALL_HOLD")
        def run(**over):
            a = dict(ok, **over)
            return review_mod.containment(S, a["found"], a["broken"], a["base"], a["binding_ok"], a["strings"], a["action"])[0]
        self.assertTrue(run())
        self.assertFalse(run(found=[]))
        self.assertFalse(run(found=[dict(ok["found"][0], source="INSTALL")]))
        self.assertFalse(run(found=[dict(ok["found"][0], reason="ALIAS_CONFLICT")]))
        self.assertFalse(run(broken=[dict(reason="OPERATION_INTERRUPTED")]))
        self.assertFalse(run(base=[dict(source="RECALL_POLICY", reason="UNREGISTERED")]))
        self.assertFalse(run(binding_ok=False))
        self.assertFalse(run(strings={S: {"ZZ-9"}, A: {review_mod.lots._skeleton("ZZ-9")}}))
        self.assertFalse(run(found=[dict(ok["found"][0], resembles=["BR-310"])], strings={S: {"ZZ-9"}, A: {review_mod.lots._skeleton("BR-310")}}))
        self.assertFalse(run(action="RELEASE_ELIGIBLE"))


class NoSilentPathToEligibility(unittest.TestCase):
    def test_retroactive_registration_of_the_sighted_string_is_held_until_reviewed_and_acknowledged(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            edit(db, lambda a: a.observe(S, "ZZ-9"))
            doc = mutated(lambda x: x["entries"].append(entry("ZZ-9")))
            s = read_snapshot(db, c0, doc)                                                                    # new registry under the old checkpoint
            self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "DISCREPANCY")
            self.assertTrue(all(not v["currentReleaseEligible"] for v in s["eligibility"].values()))


def tearDownModule():
    out = os.environ.get("SCOPED_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
