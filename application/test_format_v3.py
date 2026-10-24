"""FORMAT_V3 (registry digest inside the checkpoint's verified boundary): compatibility, threat and invariant tests. Disposable synthetic DBs, loopback only.
Run: python -B -m unittest application.test_format_v3 -v     Set V3_EVIDENCE=<file> to write the measured results as JSON.
Same-host: these tests prove the binding is covered by the checkpoint checksum, hash chain and pinning; they do not demonstrate independent custody.
"""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path



from . import checkpoint_ops
from . import lot_identity as lots
from . import registry_binding as rb
from .anchors import TrustedAnchor, export_anchor, publish_candidate, digest, FORMAT_V2, FORMAT_V3
from .audit import IntegrityFailure
from .service import Manufacturing, LedgerBlocked
from .test_lot_identity_ab import raw_assemble, entry, decision, M, RECALLED, SAFE
from .test_v11_hardening import world, read_snapshot, base_doc, mutated, reg, LEGACY

EVIDENCE = {}
V2_FIELDS = {"format", "publicationProfile", "hardeningProfile", "archiveId", "sequence", "headHash", "legacyDigest", "policyDigest", "state",
             "verifierVersion", "engineTreeId", "ledger", "previousCheckpointHash"}


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, cp):
    Path(path).write_text(json.dumps(cp), encoding="utf-8")
    return Path(path)


def reseal(cp, mutate):
    cp = copy.deepcopy(cp); mutate(cp["body"]); cp["checksum"] = digest(cp["body"]); return cp


def snap_or_fail(db, path, previous=None, doc=None):
    try:
        return read_snapshot(db, path, doc, previous)
    except IntegrityFailure as exc:
        return exc.code


class Format(unittest.TestCase):
    def test_v3_body_is_v2_plus_a_checksummed_registry_binding(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            cp = load(c0); b = cp["body"]
            self.assertEqual(b["format"], FORMAT_V3); self.assertEqual(set(b), V2_FIELDS | {"registryBinding"})
            self.assertTrue(rb.valid_block(b["registryBinding"])); self.assertEqual(b["registryBinding"]["registryDigest"], lots.LotRegistry.load(lots.DEFAULT_REGISTRY).digest)
            self.assertEqual(cp["checksum"], digest(b))
            # editing the in-body digest without resealing: checksum fails; the view is withheld (existing behaviour)
            tampered = copy.deepcopy(cp); tampered["body"]["registryBinding"]["registryDigest"] = "0" * 64
            self.assertEqual(snap_or_fail(db, write(Path(d) / "t.json", tampered)), "PREFIX_MISMATCH")
            EVIDENCE["v3BodyFields"] = sorted(b)

    def test_malformed_binding_blocks_are_integrity_failures_even_when_resealed(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d); cp = load(c0); n = 0
            muts = {"uppercase-hex": lambda b: b["registryBinding"].update(registryDigest=b["registryBinding"]["registryDigest"].upper()),
                    "short-digest": lambda b: b["registryBinding"].update(registryDigest="ab"),
                    "extra-key": lambda b: b["registryBinding"].update(extra=1),
                    "missing-key": lambda b: b["registryBinding"].pop("entryCount"),
                    "wrong-format": lambda b: b["registryBinding"].update(format="X"),
                    "wrong-provenance": lambda b: b["registryBinding"].update(provenance="REAL_SUPPLIER_ATTESTED"),
                    "bool-count": lambda b: b["registryBinding"].update(entryCount=True),
                    "null-block": lambda b: b.update(registryBinding=None),
                    "absent-block": lambda b: b.pop("registryBinding"),
                    "extra-body-field": lambda b: b.update(unexpected=1)}
            for name, m in muts.items():
                n += 1
                self.assertEqual(snap_or_fail(db, write(Path(d) / f"m{n}.json", reseal(cp, m))), "PREFIX_MISMATCH", name)
            EVIDENCE["malformedBlocks"] = len(muts)

    def test_v2_history_is_unchanged_and_v2_never_grants_current_eligibility(self):
        with tempfile.TemporaryDirectory() as d:
            db, c3, _ = world(d)
            app = Manufacturing(db); v2 = Path(d) / "c2.json"; publish_candidate(v2, export_anchor(app, version=2)); app.close()
            s3, s2 = read_snapshot(db, c3), read_snapshot(db, v2)
            self.assertEqual(s2["checkpoint"], s3["checkpoint"])                                    # identical verification outcome: state, sequence, h2
            self.assertEqual(s2["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertEqual(decision(s2)["evaluatorOperationalAction"], decision(s3)["evaluatorOperationalAction"])
            self.assertTrue(s3["eligibility"][M]["currentReleaseEligible"]); self.assertFalse(s2["eligibility"][M]["currentReleaseEligible"])
            self.assertEqual(s2["lotIdentity"]["registryBinding"]["status"], "UNBOUND_LEGACY_FORMAT")
            self.assertIn("REGISTRY_BINDING_UNBOUND_LEGACY_FORMAT", {f["reason"] for f in decision(s2)["identityGuard"]["findings"]})
            self.assertEqual(load(v2)["body"]["format"], FORMAT_V2)
            EVIDENCE["v2"] = dict(checkpoint=s2["checkpoint"], eligible=False, status="UNBOUND_LEGACY_FORMAT")

    def test_chain_rules_v2_to_v3_v3_to_v3_and_no_downgrade(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "c.sqlite"
            app = Manufacturing(db); app.create_unit(M); app.assemble(M, SAFE, "BR-312"); app.ship(M); app.announce(RECALLED, ["DE"]); app.snapshot()
            r2 = Path(d) / "r2.json"; publish_candidate(r2, export_anchor(app, version=2))
            app.create_unit("MTR-90004"); app.assemble("MTR-90004", SAFE, "BR-312"); app.ship("MTR-90004"); app.snapshot()
            c3 = export_anchor(app, load(r2)); self.assertEqual(c3["body"]["format"], FORMAT_V3)                 # V2 -> V3
            p3 = Path(d) / "c3.json"; publish_candidate(p3, c3)
            app.create_unit("MTR-90005"); app.snapshot()
            c3b = export_anchor(app, load(p3)); self.assertEqual(c3b["body"]["previousCheckpointHash"], digest(load(p3)))   # V3 -> V3
            with self.assertRaises(IntegrityFailure):
                export_anchor(app, load(p3), version=2)                                                         # no downgrade on export
            forged = reseal(dict(body=dict(c3b["body"]), checksum=""), lambda b: (b.update(format=FORMAT_V2), b.pop("registryBinding")))
            p_forged = write(Path(d) / "forged.json", forged)
            app.close()
            app = Manufacturing(db)
            try:
                TrustedAnchor(Path(d) / "c3.json", r2).verify(app)                                              # V2 -> V3 verifies
                with self.assertRaises(IntegrityFailure) as cm:                                                 # V3 -> hand-made V2 successor
                    TrustedAnchor(p_forged, p3).verify(app)
                self.assertEqual(cm.exception.code, "PREFIX_MISMATCH")
            finally:
                app.close()

    def test_registry_only_update_with_no_new_ledger_events(self):
        import application.service as S
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            doc = mutated(lambda x: x["entries"].append(entry(LEGACY)))
            regfile = Path(d) / "registry.v2.json"; regfile.write_text(json.dumps(doc), encoding="utf-8")
            S.DEFAULT_LOT_REGISTRY = regfile
            try:
                held = read_snapshot(db, c0, doc)
                self.assertEqual(held["lotIdentity"]["registryBinding"]["status"], "DISCREPANCY"); self.assertFalse(held["eligibility"][M]["currentReleaseEligible"])
                prop = checkpoint_ops.propose(db, c0, custody)
                self.assertEqual(prop["covers"]["newJournalEntries"], 0); self.assertEqual(prop["covers"]["currentAnchoredSequence"], prop["covers"]["candidateSequence"])
                self.assertEqual(load(prop["candidate"])["body"]["registryBinding"]["registryDigest"], reg(doc).digest)
                with self.assertRaises(SystemExit):
                    checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [])
                rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [], acknowledge_registry=prop["review"]["registry"]["digest"])
                s = read_snapshot(db, Path(rec["accepted"]), doc, c0)
                self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "OK"); self.assertTrue(s["eligibility"][M]["currentReleaseEligible"])
                EVIDENCE["registryOnlyUpdate"] = dict(newJournalEntries=0, accepted=True)
            finally:
                S.DEFAULT_LOT_REGISTRY = None

    def test_replay_rollback_and_substitution_matrix(self):
        import application.service as S
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            docB = mutated(lambda x: x["entries"].append(entry(LEGACY)))
            regB = Path(d) / "regB.json"; regB.write_text(json.dumps(docB), encoding="utf-8"); S.DEFAULT_LOT_REGISTRY = regB
            try:
                prop = checkpoint_ops.propose(db, c0, custody)
                rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [], acknowledge_registry=prop["review"]["registry"]["digest"])
            finally:
                S.DEFAULT_LOT_REGISTRY = None
            c1 = Path(rec["accepted"]); rows = []
            for label, path, prev, doc in (("c0+A", c0, None, None), ("c0+B", c0, None, docB), ("c1+A", c1, c0, None), ("c1+B", c1, c0, docB)):
                s = read_snapshot(db, path, doc, prev)
                rows.append(dict(label=label, binding=s["lotIdentity"]["registryBinding"]["status"], eligible=s["eligibility"][M]["currentReleaseEligible"], state=s["checkpoint"]["state"]))
            EVIDENCE["replayMatrix"] = rows
            got = {r["label"]: (r["binding"], r["eligible"]) for r in rows}
            self.assertEqual(got, {"c0+A": ("OK", True), "c0+B": ("DISCREPANCY", False), "c1+A": ("DISCREPANCY", False), "c1+B": ("OK", True)})
            # ledger advances after c1: c1 is no longer current -> not eligible even with the matching registry
            app = Manufacturing(db, lot_registry=reg(docB)); app.create_unit("MTR-90006"); app.snapshot(); app.close()
            s = read_snapshot(db, c1, docB, c0)
            self.assertNotEqual(s["checkpoint"]["state"], "ANCHORED_CURRENT"); self.assertFalse(s["eligibility"][M]["currentReleaseEligible"])
            # a pinned process detects substitution of the checkpoint file (old checkpoint put in place of the accepted one)
            app = Manufacturing(db, lot_registry=reg(docB))
            try:
                ta = TrustedAnchor(c1, c0)
                app.snapshot(trusted_anchor=ta)
                os.chmod(c1, 0o644)                                                                        # read-only mode is not a security boundary
                Path(c1).write_bytes(Path(c0).read_bytes())
                with self.assertRaises(IntegrityFailure):
                    app.snapshot(trusted_anchor=ta)
            finally:
                app.close()

    def test_missing_or_forged_live_registry_fails_closed_at_start(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            with self.assertRaises(LedgerBlocked):
                Manufacturing(db, lot_registry=Path(d) / "absent.json")
            bad = Path(d) / "forged.json"; bad.write_text(json.dumps(dict(base_doc(), provenance="REAL_SUPPLIER_ATTESTED")), encoding="utf-8")
            with self.assertRaises(LedgerBlocked):
                Manufacturing(db, lot_registry=bad)
            junk = Path(d) / "junk.json"; junk.write_text("{broken", encoding="utf-8")
            with self.assertRaises(LedgerBlocked):
                Manufacturing(db, lot_registry=junk)


class NeverCreatesEligibility(unittest.TestCase):
    """A checkpoint-format change (V2 to V3, V3 renewal, forged V3 root) never makes an identity-unsafe motor eligible."""
    UNSAFE = "MTR-90003"

    def build(self, d):
        db, v2, custody = Path(d) / "u.sqlite", Path(d) / "v2.json", Path(d) / "custody"
        app = Manufacturing(db); app.create_unit(M); app.create_unit(self.UNSAFE)
        app.assemble(M, SAFE, "BR-312"); app.ship(M)
        raw_assemble(app, self.UNSAFE, "UNKNOWN", SAFE); app.ship(self.UNSAFE)             # bypassed capture: the evaluator alone would exclude and release it
        app.announce(RECALLED, ["DE"]); app.snapshot()
        publish_candidate(v2, export_anchor(app, version=2)); app.close()
        return db, v2, custody

    def assert_unsafe_held(self, s, label):
        c = decision(s, self.UNSAFE)
        self.assertEqual(c["evaluatorOperationalAction"], "RELEASE_ELIGIBLE", label)       # the evaluator would release it
        self.assertEqual(c["operationalAction"], "RECALL_HOLD", label)
        self.assertFalse(s["eligibility"][self.UNSAFE]["currentReleaseEligible"], label)
        self.assertIn("SENTINEL", {f["reason"] for f in c["identityGuard"]["findings"]}, label)

    def test_v2_to_v3_migration_cannot_launder_an_unsafe_motor(self):
        with tempfile.TemporaryDirectory() as d:
            db, v2, custody = self.build(d)
            self.assert_unsafe_held(read_snapshot(db, v2), "v2")
            prop = checkpoint_ops.propose(db, v2, custody)
            self.assertEqual(prop["review"]["refusedForIdentity"], [self.UNSAFE])
            with self.assertRaises(SystemExit) as cm:                                         # every acknowledgement supplied, still refused
                checkpoint_ops.accept(db, v2, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [M, self.UNSAFE], acknowledge_registry=prop["review"]["registry"]["digest"])
            self.assertIn("not established", str(cm.exception)); self.assertFalse((custody / "accepted").exists())
            # the candidate bypassing review (operator exports it directly and pins it): the guard still holds the motor
            cand = Path(prop["candidate"])
            self.assertEqual(load(cand)["body"]["format"], FORMAT_V3)
            s = read_snapshot(db, cand, None, v2)
            self.assertEqual(s["lotIdentity"]["registryBinding"]["status"], "OK")
            self.assert_unsafe_held(s, "v3 candidate pinned without review"); self.assertTrue(s["eligibility"][M]["currentReleaseEligible"])
            EVIDENCE["unsafeMotorAcrossFormats"] = dict(v2="held", v3Candidate="held", acceptWithAllAcknowledgements="REFUSED")

    def test_v3_root_renewal_and_forged_v3_conversion_cannot_launder_an_unsafe_motor(self):
        with tempfile.TemporaryDirectory() as d:
            db, v2, custody = self.build(d)
            app = Manufacturing(db); root = Path(d) / "v3root.json"; publish_candidate(root, export_anchor(app)); app.close()   # fresh V3 root, no predecessor
            self.assert_unsafe_held(read_snapshot(db, root), "v3 root")
            conv = write(Path(d) / "converted.json", reseal(load(v2), lambda b: (b.update(format=FORMAT_V3, registryBinding=rb.binding_block(lots.LotRegistry.load(lots.DEFAULT_REGISTRY))))))
            self.assert_unsafe_held(read_snapshot(db, conv), "v2 body relabelled as v3 and resealed")
            prop = checkpoint_ops.propose(db, root, custody) if checkpoint_ops else None
            self.assertEqual(prop["status"], "NO_CANDIDATE_NEEDED")                                  # nothing to renew; and the unsafe motor remains held
            app = Manufacturing(db); app.create_unit("MTR-90007"); app.snapshot(); app.close()       # ledger advances; renewal proposed
            prop = checkpoint_ops.propose(db, root, custody)
            self.assertEqual(prop["review"]["refusedForIdentity"], [self.UNSAFE])
            with self.assertRaises(SystemExit):
                checkpoint_ops.accept(db, root, custody, Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [M, self.UNSAFE])


def tearDownModule():
    out = os.environ.get("V3_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
