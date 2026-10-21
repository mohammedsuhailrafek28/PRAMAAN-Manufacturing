"""v3: untrusted affected-bearing observations hold a release; semantics profiles and legacy replay.

Adversarial tests 1-7 correspond to the review proposal; test 8 (mutation) is
harness/mutation_check.py, run once by MutantsAreKilled below.
"""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import unittest

from tests import helpers as h
from harness import compare_profiles as CP
from harness import oracle_harness as H
from pramaan_recall import Config, evaluate, evaluate_series, replay

EXCL, AFF, UNRES = "EXCLUDED_WITH_EVIDENCE", "AFFECTED", "UNRESOLVED"
UAO = "UNTRUSTED_AFFECTED_OBSERVATION"
FIX3 = os.path.join(h.ROOT, "fixtures", "v3")
POL3, COV3 = H.load_policies(os.path.join(FIX3, "policies.json"))


def _b3():
    spec = importlib.util.spec_from_file_location("build_v3", os.path.join(FIX3, "build_v3.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B3 = _b3()


def run3(c, pid=h.P1, wm=None, cov=None, cfg=None):
    return evaluate(c, copy.deepcopy(POL3[pid]), cov or copy.deepcopy(COV3), wm, cfg or Config.v3())


def cov3():
    return copy.deepcopy(COV3)


def case3(name):
    path = os.path.join(FIX3, "cases", f"case-{name}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clean(prefix="T", **kw):
    """Distinct-lot replacement (releasable), plus one untrusted handheld reading."""
    kw.setdefault("lot", "BR-204")
    lot = kw.pop("lot")
    return B3.with_obs(B3.clean("t", prefix, "t", "t"), prefix, lot, **kw)


def qa_check(c, lot, at="2026-09-10T12:00:00Z", rec=None, actor="EMP-031", source="QA-02", **payload):
    pl = dict(componentType="BEARING", slot="DE", observedPart="BR-6205", observedLot=lot,
              method="LOT_LABEL_AND_MARKING_VISUAL")
    pl.update(payload)
    e = B3.b2.ev("T", 95, "SLOT_STATE_VERIFIED", source, at, rec or B3.plus4(at), actor, pl, refs=["EV-PHOTO-0399"])
    c["events"].append(e)
    if not any(s["sourceId"] == "QA-02" for s in c["captureCoverage"]["sessions"]):
        c["captureCoverage"]["sessions"].append(
            dict(sourceId="QA-02", **{"from": "2026-09-10T11:45:00Z", "to": "2026-09-10T13:00:00Z"}))
    c["_prefix"] = "T"
    return B3.b2.finish(c)


def status(d):
    return {o["eventId"]: o["status"] for o in d["untrustedObservations"]}


class UntrustedObservationBlocker(unittest.TestCase):
    # -- test 1
    def test_1_untrusted_source_affected_observation_holds_but_is_never_affected(self):
        for pid in (h.P1, h.P2):
            d = run3(clean(), pid)
            self.assertNotEqual(d["evidenceFinding"], AFF if pid == h.P1 else None)
            if pid == h.P1:
                self.assertEqual((d["evidenceFinding"], d["operationalAction"], d["reviewRequired"], d["reasonCodes"]),
                                 (UNRES, "RECALL_HOLD", True, [UAO]))
                self.assertEqual(list(status(d).values()), ["BLOCKING"])
                self.assertIn(next(iter(status(d))), d["evidenceEventIds"])

    def test_1b_history_free_motor_is_held_not_affected_under_both_policies(self):
        c = B3.with_obs(B3.b2.base("t", "T", "t", "t", lots=("BR-500", "BR-310"), new_lot="BR-312"), "T", "BR-204")
        self.assertEqual(run3(c)["evidenceFinding"], UNRES)
        p2 = run3(c, h.P2)
        self.assertEqual((p2["evidenceFinding"], p2["reasonCodes"]), (UNRES, [UAO]))
        self.assertEqual(run3(c, cfg=Config.v2())["evidenceFinding"], EXCL)        # the old blind spot

    # -- test 2
    def test_2_trusted_source_failing_independence_still_holds(self):
        mutations = {
            "METHOD_NOT_APPROVED": dict(method="HEARSAY"),
            "ACTOR_NOT_INDEPENDENT": dict(actor="EMP-017"),
            "ACTOR_NOT_AUTHORIZED": dict(actor="EMP-099"),
            "EVIDENCE_NOT_INDEPENDENT": dict(evidenceRefs=["EV-SCAN-0202"]),
        }
        for reason, kw in mutations.items():
            with self.subTest(reason):
                c = B3.b2.base("t", "T", "t", "t", lots=("BR-204", "BR-310"), new_lot="BR-312")
                actor = kw.pop("actor", "EMP-031")
                pl = {k: v for k, v in kw.items() if k != "evidenceRefs"}
                c = qa_check(c, "BR-204", actor=actor, **pl)
                if "evidenceRefs" in kw:
                    c["events"][-1]["evidenceRefs"] = kw["evidenceRefs"]
                    c["events"].sort(key=lambda e: e["recordedAt"])
                d = run3(c)
                self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, [UAO]))
                self.assertIn(reason, d["untrustedObservations"][0]["rejectedReasons"])

    def test_2b_derived_from_the_claim_and_same_source_hold(self):
        c = B3.b2.base("t", "T", "t", "t", lots=("BR-204", "BR-310"), new_lot="BR-312")
        inst = next(e["eventId"] for e in c["events"] if e["eventType"] == "COMPONENT_INSTALLED"
                    and e["workOrderId"] == "RW-192")
        d = run3(qa_check(c, "BR-204", derivedFromEventIds=[inst]))
        self.assertEqual(d["reasonCodes"], [UAO])
        c = B3.b2.base("t", "T", "t", "t", lots=("BR-204", "BR-310"), new_lot="BR-312")
        cov = cov3()
        cov["trustedVerifierSources"].append("REWORK-03")
        c = qa_check(c, "BR-204", source="REWORK-03", at="2026-09-10T12:00:00Z")
        d = run3(c, cov=cov)
        self.assertIn("SOURCE_NOT_INDEPENDENT", d["untrustedObservations"][0]["rejectedReasons"])
        self.assertEqual(d["reasonCodes"], [UAO])

    def test_2c_a_trusted_verification_is_not_an_untrusted_observation(self):
        c = qa_check(B3.b2.base("t", "T", "t", "t", lots=("BR-204", "BR-310"), new_lot="BR-312"), "BR-204")
        d = run3(c)
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (AFF, ["VERIFIED_AFFECTED_LOT_PRESENT"]))
        self.assertEqual(d["untrustedObservations"], [])

    # -- test 3
    def test_3_observation_provably_older_than_the_replacement_does_not_block(self):
        d = run3(case3("08g"))
        self.assertEqual((d["evidenceFinding"], d["reviewRequired"]), (EXCL, False))
        self.assertIn("UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED", d["flags"])
        self.assertEqual(list(status(d).values()), ["STALE"])

    def test_3b_clock_skew_margin_is_strict(self):
        for obs_at, expect in (("2026-09-10T10:54:59Z", EXCL), ("2026-09-10T10:55:00Z", UNRES)):
            with self.subTest(obs_at):          # replacement recorded 11:00:00; margin is > 300 s
                c = clean(at=obs_at, session=("2026-09-10T08:00:00Z", "2026-09-10T12:00:00Z"))
                self.assertEqual(run3(c)["evidenceFinding"], expect)

    def test_3c_time_uncertainty_never_closes_a_risk(self):
        for name in ("08j", "08k"):             # operator-entered clock / arrived after the replacement
            with self.subTest(name):
                d = run3(case3(name))
                self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, [UAO]))

    def test_3d_missing_time_parameters_fail_safe(self):
        cov = cov3()
        del cov["slotAttribution"]["observationClockSkewSeconds"]
        self.assertEqual(run3(case3("08g"), cov=cov)["evidenceFinding"], UNRES)
        cov = cov3()
        cov["slotAttribution"]["trustedTimeSources"] = []
        self.assertEqual(run3(case3("08g"), cov=cov)["evidenceFinding"], UNRES)

    def test_3e_resolution_needs_a_provably_later_independent_check(self):
        self.assertEqual(run3(case3("08f"))["evidenceFinding"], EXCL)
        late = lambda **kw: clean(rec="2026-09-10T11:55:00Z", **kw)           # obs recorded 11:55
        d = run3(qa_check(late(), "BR-312", at="2026-09-10T11:50:00Z"))        # check recorded earlier
        self.assertEqual(d["evidenceFinding"], UNRES)
        d = run3(qa_check(clean(), "BR-312", at="2026-09-10T11:33:00Z"))         # inside the skew margin
        self.assertEqual(d["evidenceFinding"], UNRES)
        d = run3(qa_check(clean(), "BR-312", at="2026-09-10T11:50:00Z"))         # provably later
        self.assertEqual(d["evidenceFinding"], EXCL)

    # -- test 4
    def test_4_out_of_scope_observation_is_visible_but_does_not_block(self):
        d = run3(case3("08h"))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertTrue(d["reviewRequired"])
        self.assertIn("OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION", d["flags"])
        self.assertEqual(list(status(d).values()), ["OUT_OF_SCOPE"])

    def test_4b_other_motor_or_missing_slot_is_not_attributable(self):
        d = run3(case3("08l"))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertIn("UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION", d["flags"])
        self.assertTrue(d["reviewRequired"])
        c = clean()
        del next(e for e in c["events"] if e["sourceId"] == B3.SRC)["payload"]["slot"]
        d = run3(c)
        self.assertEqual((d["evidenceFinding"], d["untrustedObservations"][0]["status"]), (EXCL, "UNATTRIBUTABLE"))

    # -- test 5
    def test_5_untrusted_unaffected_observation_never_releases(self):
        d = run3(case3("08i"))                                  # ambiguous removal + untrusted BR-310
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, ["AMBIGUOUS_SLOT_ATTRIBUTION"]))
        c = B3.with_obs(B3.b2.base("t", "T", "t", "t", lots=("BR-204", "BR-310"), new_lot="BR-207"), "T", "BR-310")
        self.assertEqual(run3(c)["evidenceFinding"], AFF)       # records say affected; reading does not clear it
        c = clean(lot="BR-310")
        h.add_event(c, "CAPTURE_EXCEPTION_RAISED", "MES", "2026-09-10T09:00:00Z", "SYS-MES",
                    {"scope": {"slots": ["DE"]}})
        d = run3(h.renumber(c))
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertNotIn(UAO, d["reasonCodes"])

    def test_5b_untrusted_unaffected_observation_does_not_block_either(self):
        d = run3(clean(lot="BR-312"))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertEqual(list(status(d).values()), ["UNAFFECTED"])

    # -- test 6
    def test_6_late_arrival_after_release_withdraws_the_exclusion(self):
        c = case3("08")
        obs = next(e for e in c["events"] if e["sourceId"] == B3.SRC)
        base = B3.wm(c, drop=(B3.SRC,))
        series = evaluate_series(c, copy.deepcopy(POL3[h.P1]), cov3(), [base, B3.wm(c)],
                                 Config.v3(), communicated=("D-case-08-P1-v1",))
        v1, v2 = series
        self.assertEqual((v1["evidenceFinding"], v1["operationalAction"]), (EXCL, "RELEASE_ELIGIBLE"))
        self.assertEqual((v2["evidenceFinding"], v2["operationalAction"], v2["reviewRequired"]),
                         (UNRES, "RECALL_HOLD", True))
        self.assertEqual(v2["supersedesDecisionId"], v1["decisionId"])
        self.assertEqual(v2["triggerEventId"], obs["eventId"])
        self.assertTrue(v2["precautionaryHold"])
        self.assertIn("PRIOR_EXCLUSION_WITHDRAWN", v2["reasonCodes"])
        self.assertEqual(v2["notificationObligation"], dict(
            required=True, reason="PRIOR_EXCLUSION_WITHDRAWN",
            appliesIfDecisionCommunicated=v1["decisionId"], communicated=True))
        self.assertEqual(v1["evidenceFinding"], EXCL)           # history is kept, never edited

    # -- test 7
    def test_7_conflicting_untrusted_observations_hold(self):
        c = clean()
        e = copy.deepcopy(next(x for x in c["events"] if x["sourceId"] == B3.SRC))
        e.update(eventId="T-X2", occurredAt="2026-09-10T11:31:00Z", recordedAt="2026-09-10T11:31:04Z")
        e["payload"]["observedLot"] = "BR-312"
        c["events"].append(e)
        d = run3(h.renumber(c))
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, [UAO]))
        self.assertEqual(sorted(status(d).values()), ["BLOCKING", "UNAFFECTED"])

    def test_untrusted_observation_requires_slot_attribution(self):
        with self.assertRaises(ValueError):
            evaluate(case3("08"), copy.deepcopy(POL3[h.P1]), cov3(), None, Config(untrusted_observation=True))

    def test_v2_oracle_cases_are_unchanged_under_v3(self):
        self.assertEqual([r for r in H.run_behavioral(H.V3_CONFIG, 2, 3) if r["decisionDiffs"] or r["detailDiffs"]], [])


class ProfilesAndLegacyReplay(unittest.TestCase):
    def test_default_config_object_is_still_legacy_but_new_evaluations_use_v3(self):
        self.assertEqual(Config().profile, "P1_LEGACY")
        self.assertEqual(Config.default().profile, "UNTRUSTED_OBSERVATION_V3")
        d = evaluate(h.case("06"), h.policy(h.P1), h.COVERAGE2 if hasattr(h, "COVERAGE2") else h.COVERAGE2, None)
        self.assertEqual((d["evidenceFinding"], d["semanticsProfile"]), (UNRES, "UNTRUSTED_OBSERVATION_V3"))

    def test_lifecycle_default_is_v3_and_legacy_is_explicit(self):
        pol = h.policy(h.P1)
        new = evaluate_series(h.case("06"), pol, h.COVERAGE2, [None])[0]
        old = evaluate_series(h.case("06"), pol, h.COVERAGE, [None], Config.legacy())[0]
        self.assertEqual((new["evidenceFinding"], old["evidenceFinding"]), (UNRES, EXCL))
        self.assertEqual((new["semanticsProfile"], old["semanticsProfile"]), ("UNTRUSTED_OBSERVATION_V3", "P1_LEGACY"))

    def test_stored_legacy_decision_replays_unchanged_while_new_evaluation_differs(self):
        c, pol = h.case("06"), h.policy(h.P1)
        stored = evaluate(c, pol, h.COVERAGE, None, Config.legacy())
        self.assertEqual(stored["evidenceFinding"], EXCL)
        again = replay(c, pol, h.COVERAGE, stored)
        self.assertEqual((again["evidenceFinding"], again["reasonCodes"], again["flags"]),
                         (EXCL, stored["reasonCodes"], stored["flags"]))
        fresh = evaluate(c, pol, h.COVERAGE2, None)
        self.assertEqual(fresh["evidenceFinding"], UNRES)

    def test_records_written_before_profiles_existed_replay_as_legacy(self):
        c, pol = h.case("06"), h.policy(h.P1)
        old = evaluate(c, pol, h.COVERAGE, None, Config.legacy())
        for k in ("semanticsProfile", "coverageDigest"):
            old.pop(k)
        self.assertEqual(replay(c, pol, h.COVERAGE, old)["evidenceFinding"], EXCL)

    def test_replay_refuses_a_different_coverage_policy_and_unknown_profiles(self):
        c, pol = h.case2("06f"), h.policy(h.P1)
        rec = evaluate(c, pol, h.cov2(), None, Config.v2())
        other = h.cov2()
        other["slotAttribution"]["labelAssociationWindowSeconds"] = 5
        with self.assertRaises(ValueError):
            replay(c, pol, other, rec)
        with self.assertRaises(ValueError):
            replay(c, pol, h.cov2(), dict(rec, semanticsProfile="NOPE"))

    def test_every_oracle_version_reproduces_under_its_own_profile(self):
        r = CP.compute()
        self.assertTrue(r["gate"]["pass"], r["gate"])
        for label, v in r["legacyReplay"].items():
            self.assertEqual(v["records"], v["reproduced"], label)
        self.assertEqual((r["A"]["E1/O1"]["fullAgree"], r["A"]["E2/O2"]["fullAgree"], r["A"]["E3/O3"]["fullAgree"]),
                         (25, 35, 54))

    def test_gate_would_fail_for_a_profile_that_still_releases_08(self):
        bad = CP.compute(e3_config=Config.v2())
        self.assertFalse(bad["gate"]["pass"])
        self.assertIn("case-08 P1", bad["B"]["false_releases"]["E3"])

    def test_v3_fixture_set_is_preserved_and_reproducible(self):
        import hashlib
        with open(os.path.join(FIX3, "MANIFEST.sha256"), encoding="utf-8") as m:
            for line in m.read().splitlines():
                digest, path = line.strip().split(" *", 1)
                with open(os.path.join(FIX3, path), "rb") as f:
                    self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest, path)
        cases = B3.build_cases()
        with open(os.path.join(FIX3, "oracle-v3.json"), encoding="utf-8") as f:
            v3 = json.load(f)
        self.assertEqual(v3, B3.build_oracle(cases))
        with open(os.path.join(h.FIX2, "oracle-v2.json"), encoding="utf-8") as f:
            v2 = json.load(f)
        self.assertEqual(v3["cases"][:len(v2["cases"])], v2["cases"])
        self.assertEqual(v3["derivedFrom"]["sha256"], B3.b2.sha(os.path.join(h.FIX2, "oracle-v2.json")))
        for cid, c in cases.items():
            with open(os.path.join(FIX3, "cases", f"{cid}.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f), c)

    def test_engine_has_no_v3_fixture_identifiers(self):
        import re
        pkg = os.path.join(h.ROOT, "pramaan_recall")
        for f in os.listdir(pkg):
            if f.endswith(".py"):
                with open(os.path.join(pkg, f), encoding="utf-8") as fh:
                    self.assertIsNone(re.search(r"HANDHELD|case-08|C08|EMP-0|BR-\d", fh.read()), f)


@unittest.skipIf(os.environ.get("MUTATION_RUN"), "already inside a mutation run")
class MutantsAreKilled(unittest.TestCase):
    # -- test 8
    def test_8_every_mutant_of_the_v3_safety_logic_is_caught(self):
        out = subprocess.run([sys.executable, os.path.join(h.ROOT, "harness", "mutation_check.py"), "--quiet"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("survived: 0", out.stdout)


if __name__ == "__main__":
    unittest.main()
