"""Builds the version-2 fixture set from the untouched version-1 archive.

Run: python build_v2.py        (writes cases/, policies.json, oracle-v2.json, ground-truth.json,
                                VERSION_TRANSITION.json/.md, MANIFEST.sha256 next to this file)

Version 1 (../pramaan-mfg-fixtures/) is read, never written. v2 expectations for changed and
new evaluations are written by hand below; they are NOT derived from engine output.
"""
import copy
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(HERE, "..", "pramaan-mfg-fixtures")
P1, P2 = "RC-009/P1", "RC-009/P2"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------------- policies ----
def build_policies():
    d = copy.deepcopy(load(os.path.join(V1, "policies.json")))
    d["coveragePolicy"]["slotAttribution"] = {
        "version": 2,
        "note": "Prototype parameters, not a proven safety standard.",
        "labelAssociationWindowSeconds": 60,
        "unknownSlotIsCandidate": True,
        "labelScanSources": ["ASSY-01", "REWORK-03"],
        "slotLabels": [
            dict(labelId=f"LBL-M042-{s}", motorSerial="M-042", slot=s, status="ACTIVE",
                 provisionedAt="2026-08-01T00:00:00Z", revokedAt=None) for s in ("DE", "NDE")],
        "approvedVerificationMethods": [
            "LOT_LABEL_AND_MARKING_VISUAL", "SERIAL_MARKING_VISUAL", "DISASSEMBLY_INSPECTION"],
        "authorizedVerifierActors": ["EMP-031"],
        "accessEvidenceSources": ["QA-02"],
        "approvedAccessMethods": ["DISASSEMBLY_RECORD", "STATION_FIXTURE_RECORD"],
    }
    return d


# ---------------------------------------------------------------- cases ----
def ev(prefix, n, etype, source, occurred, recorded, actor, payload, wo=None, refs=()):
    return dict(eventId=f"{prefix}-E{n:03d}", eventType=etype, schemaVersion=1, sourceId=source,
                sourceSeq=0, motorSerial="M-042", workOrderId=wo, recallId=None,
                occurredAt=occurred, timeSource="DEVICE_SYNCED", recordedAt=recorded,
                actorId=actor, evidenceRefs=list(refs), supersedesEventId=None, payload=payload)


def finish(case):
    """Order by recordedAt, renumber ids and per-source sequences, rewire links."""
    evs = sorted(case["events"], key=lambda e: (e["recordedAt"], e["occurredAt"], e["eventId"]))
    prefix = case["_prefix"]
    remap = {e["eventId"]: f"{prefix}-E{i + 1:03d}" for i, e in enumerate(evs)}
    seq = {}
    for e in evs:
        e["eventId"] = remap[e["eventId"]]
        seq[e["sourceId"]] = seq.get(e["sourceId"], 0) + 1
        e["sourceSeq"] = seq[e["sourceId"]]
        if e["payload"].get("endsInstallEventId"):
            e["payload"]["endsInstallEventId"] = remap[e["payload"]["endsInstallEventId"]]
    case["events"] = evs
    del case["_prefix"]
    return case


def base(caseid, prefix, title, desc, lots=("BR-204", "BR-204"), new_lot="BR-310",
        serials=None, label=None, verify=None):
    """Build + rework(replace DE) history shaped like case-06. `label` = (seconds before removal,
    labelId) adds a SLOT_LABEL_SCANNED; `verify` = observed lot adds an independent QA-02 check."""
    ser = serials or {}
    gran = "SERIAL" if serials else "LOT"
    pl = lambda slot, lot, **kw: dict(componentType="BEARING", slot=slot, part="BR-6205", lot=lot,
                                      identityGranularity=gran, **kw)
    sessions = [dict(sourceId="MES", **{"from": "2026-08-01T00:00:00Z", "to": "2026-10-31T00:00:00Z"}),
                dict(sourceId="ASSY-01", **{"from": "2026-08-12T08:00:00Z", "to": "2026-08-12T18:00:00Z"}),
                dict(sourceId="REWORK-03", **{"from": "2026-09-10T08:00:00Z", "to": "2026-09-10T18:00:00Z"})]
    e = []
    n = iter(range(1, 99))
    e.append(ev(prefix, next(n), "WORK_ORDER_OPENED", "MES", "2026-08-12T09:30:00Z", "2026-08-12T09:30:04Z",
                "SYS-MES", dict(orderType="BUILD", expectedChanges=[dict(slot="DE", action="INSTALL"),
                                                                    dict(slot="NDE", action="INSTALL")]),
                wo="MO-042"))
    for slot, lot, t, ref in (("DE", lots[0], "10:00:00", "EV-SCAN-0101"), ("NDE", lots[1], "10:05:00", "EV-SCAN-0102")):
        extra = dict(serial=ser[slot]) if slot in ser else {}
        e.append(ev(prefix, next(n), "COMPONENT_INSTALLED", "ASSY-01", f"2026-08-12T{t}Z",
                    f"2026-08-12T{t[:-2]}04Z", "EMP-009", pl(slot, lot, **extra), wo="MO-042", refs=[ref]))
    e.append(ev(prefix, next(n), "WORK_ORDER_CLOSED", "MES", "2026-08-12T11:00:00Z", "2026-08-12T11:00:04Z",
                "SYS-MES", dict(disposition="COMPLETED"), wo="MO-042"))
    e.append(ev(prefix, next(n), "WORK_ORDER_OPENED", "MES", "2026-09-10T08:45:00Z", "2026-09-10T08:45:04Z",
                "SYS-MES", dict(orderType="REWORK", reason="NCR-0771 bearing noise",
                                expectedChanges=[dict(slot="DE", action="REPLACE")]), wo="RW-192"))
    rem = dict(componentType="BEARING", slot="DE", endsInstallEventId=f"{prefix}-E002", observedPart="BR-6205",
               observedLot=lots[0], identityGranularity=gran)
    if serials:
        rem["observedSerial"] = serials["REMOVED"]
    first = e[1]["eventId"]
    rem["endsInstallEventId"] = first
    e.append(ev(prefix, next(n), "COMPONENT_REMOVED", "REWORK-03", "2026-09-10T10:00:00Z", "2026-09-10T10:00:04Z",
                "EMP-017", rem, wo="RW-192", refs=["EV-SCAN-0201"]))
    new = pl("DE", new_lot, **(dict(serial=serials["NEW"]) if serials else {}))
    e.append(ev(prefix, next(n), "COMPONENT_INSTALLED", "REWORK-03", "2026-09-10T11:00:00Z", "2026-09-10T11:00:04Z",
                "EMP-017", new, wo="RW-192", refs=["EV-SCAN-0202"]))
    e.append(ev(prefix, next(n), "WORK_ORDER_CLOSED", "MES", "2026-09-10T11:15:00Z", "2026-09-10T11:15:04Z",
                "SYS-MES", dict(disposition="COMPLETED"), wo="RW-192"))
    if label:
        secs, lid = label
        t = 10 * 3600 - secs
        hms = f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"
        e.append(ev(prefix, next(n), "SLOT_LABEL_SCANNED", "REWORK-03", f"2026-09-10T{hms}Z",
                    f"2026-09-10T{hms[:-2]}{t % 60 + 4:02d}Z", "EMP-017", dict(labelId=lid),
                    wo="RW-192", refs=["EV-LBL-0201"]))
    if verify:
        sessions.append(dict(sourceId="QA-02", **{"from": "2026-09-10T11:00:00Z", "to": "2026-09-10T12:00:00Z"}))
        e.append(ev(prefix, next(n), "SLOT_STATE_VERIFIED", "QA-02", "2026-09-10T11:30:00Z", "2026-09-10T11:30:04Z",
                    "EMP-031", dict(componentType="BEARING", slot="DE", observedPart="BR-6205", observedLot=verify,
                                    method="LOT_LABEL_AND_MARKING_VISUAL"), refs=["EV-PHOTO-0311"]))
    return finish(dict(caseId=caseid, title=title, description=desc, _prefix=prefix,
                       captureCoverage=dict(coveragePolicy="COV-BEARING-v1", sessions=sessions), events=e))


def build_cases():
    c = {}
    c["case-06c"] = base(
        "case-06c", "C06C", "Wrong-slot scan, valid slot-label scan, no independent verification",
        "As case-06, plus a valid DE slot-label scan 20 s before the removal scan. The technician scanned "
        "the DE label but physically replaced NDE. A label scan shows operator intent, not physical position.",
        label=(20, "LBL-M042-DE"))
    c["case-06c"]["groundTruth"] = {"DE": "BR-204", "NDE": "BR-310", "trueP1Finding": "AFFECTED",
                                    "note": "label scan was valid but the physical removal was from NDE"}
    c["case-06d"] = base(
        "case-06d", "C06D", "Serialized removal conflicts with the recorded slot",
        "Serial-level identity. The removal claims DE but reads serial SN-204-0002, which the installation "
        "record places in NDE. DE therefore still holds SN-204-0001 (lot BR-204).",
        serials=dict(DE="SN-204-0001", NDE="SN-204-0002", REMOVED="SN-204-0002", NEW="SN-310-0007"))
    c["case-06d"]["groundTruth"] = {"DE": "BR-204", "NDE": "BR-310", "trueP1Finding": "AFFECTED",
                                    "note": "the bearing physically removed was NDE's SN-204-0002"}
    c["case-06e"] = base(
        "case-06e", "C06E", "Correct replacement, indistinguishable from case-06c",
        "Events identical to case-06c (valid DE label scan, lot-level identity, no verification) but the "
        "technician really did replace DE. Same records, opposite physical truth: the cost of not guessing.",
        label=(20, "LBL-M042-DE"))
    c["case-06e"]["groundTruth"] = {"DE": "BR-310", "NDE": "BR-204", "trueP1Finding": "UNAFFECTED",
                                    "note": "DE really was replaced; the engine cannot know that"}
    c["case-06f"] = base(
        "case-06f", "C06F", "Valid label scan plus independent QA verification of DE",
        "As case-06e, plus an independent QA-02 physical check observing BR-310 in DE.",
        label=(20, "LBL-M042-DE"), verify="BR-310")
    c["case-06f"]["groundTruth"] = {"DE": "BR-310", "NDE": "BR-204", "trueP1Finding": "UNAFFECTED",
                                    "note": "independent physical check agrees with the records"}
    c["case-07"] = base(
        "case-07", "C07", "Distinct lots, no attribution ambiguity",
        "DE holds BR-204 and NDE holds BR-310 (different lots). DE replaced with BR-312. A lot-level removal "
        "scan can only have come from DE, so nothing is ambiguous and no extra evidence is needed.",
        lots=("BR-204", "BR-310"), new_lot="BR-312")
    c["case-07"]["groundTruth"] = {"DE": "BR-312", "NDE": "BR-310", "trueP1Finding": "UNAFFECTED",
                                   "note": "unambiguous replacement"}
    return c


# --------------------------------------------------- hand-written oracle ----
def wm(case):
    out = {}
    for e in case["events"]:
        out[e["sourceId"]] = max(out.get(e["sourceId"], 0), e["sourceSeq"])
    return dict(sorted(out.items(), key=lambda kv: ["MES", "ASSY-01", "REWORK-03", "QA-02"].index(kv[0])))


def slot(reconciliation, lot, gran="LOT"):
    return {"DE": dict(reconciliation=reconciliation, baseline="AS_BUILT_VALIDATED", identityGranularity=gran,
                       policyRelevance="RELEVANT", currentLotPerRecords=lot)}


def with_conflicts(slots, conflicts):
    slots["DE"]["conflicts"] = conflicts
    return slots


def entry(case, pid, finding, review, reasons, slots, flags=None, note=None):
    d = dict(policyId=pid, watermark=wm(case), decisionId=f"D-{case['caseId']}-{pid[-2:]}",
             evidenceFinding=finding,
             operationalAction="RELEASE_ELIGIBLE" if finding == "EXCLUDED_WITH_EVIDENCE" else "RECALL_HOLD",
             reviewRequired=review, reasonCodes=reasons, slots=slots)
    if flags:
        d["flags"] = flags
    if note:
        d["notes"] = note
    return d


P2_REASONS = ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"]
AMBIG_NOTE = ("v2: removal of an affected lot whose part+lot match more than one accessible slot; only "
              "CORROBORATED_SLOT clears it. Ambiguity is not proof of a wrong-slot removal.")


def oracle_entries(cases):
    """caseId -> list of evaluations for v2-new cases."""
    out = {}
    for cid in ("case-06c", "case-06e"):
        c = cases[cid]
        out[cid] = [entry(c, P1, "UNRESOLVED", True, ["AMBIGUOUS_SLOT_ATTRIBUTION"],
                          slot("AMBIGUOUS_ATTRIBUTION", "BR-310"), note=AMBIG_NOTE),
                    entry(c, P2, "AFFECTED", False, P2_REASONS, slot("AMBIGUOUS_ATTRIBUTION", "BR-310"))]
    c = cases["case-06d"]
    de_inst = next(e["eventId"] for e in c["events"] if e["eventType"] == "COMPONENT_INSTALLED"
                   and e["payload"]["slot"] == "DE" and e["workOrderId"] == "MO-042")
    nde_inst = next(e["eventId"] for e in c["events"] if e["eventType"] == "COMPONENT_INSTALLED"
                    and e["payload"]["slot"] == "NDE")
    conflicts = [dict(kind="REMOVAL_OBSERVATION_MISMATCH", occupiedBy=de_inst),
                 dict(kind="REMOVAL_SERIAL_IN_OTHER_SLOT", otherSlot="NDE", installEventId=nde_inst)]
    out["case-06d"] = [
        entry(c, P1, "UNRESOLVED", True,
              ["REMOVAL_OBSERVATION_MISMATCH", "REMOVAL_SERIAL_IN_OTHER_SLOT", "CURRENT_STATE_UNVERIFIED"],
              with_conflicts(slot("CONFLICT", "BR-310", "SERIAL"), conflicts),
              note="v2: removal serial matches the serial installed in NDE, not the claimed slot."),
        entry(c, P2, "AFFECTED", False, P2_REASONS,
              with_conflicts(slot("CONFLICT", "BR-310", "SERIAL"), conflicts),
              flags=["SLOT_RECORD_CONFLICT"])]
    c = cases["case-06f"]
    out["case-06f"] = [
        entry(c, P1, "EXCLUDED_WITH_EVIDENCE", False, ["REPLACED_WITH_UNAFFECTED_LOT"], slot("CLEAN", "BR-310"),
              note="v2: independent CORROBORATED_SLOT check clears the ambiguity for current installation."),
        entry(c, P2, "AFFECTED", False, P2_REASONS, slot("CLEAN", "BR-310"),
              note="Historical exposure is not erased by current-state verification.")]
    c = cases["case-07"]
    out["case-07"] = [
        entry(c, P1, "EXCLUDED_WITH_EVIDENCE", False, ["REPLACED_WITH_UNAFFECTED_LOT"], slot("CLEAN", "BR-312")),
        entry(c, P2, "AFFECTED", False, P2_REASONS, slot("CLEAN", "BR-312"))]
    return out


def build_oracle(cases):
    v1 = load(os.path.join(V1, "oracle.json"))
    o = dict(oracleVersion=2,
             derivedFrom=dict(oracleVersion=1, file="../pramaan-mfg-fixtures/oracle.json",
                              sha256=sha(os.path.join(V1, "oracle.json"))),
             cases=copy.deepcopy(v1["cases"]))
    for oc in o["cases"]:
        if oc["caseId"] != "case-06":
            continue
        for ev_ in oc["evaluations"]:
            if ev_["policyId"] == P1:
                ev_.update(evidenceFinding="UNRESOLVED", operationalAction="RECALL_HOLD", reviewRequired=True,
                           reasonCodes=["AMBIGUOUS_SLOT_ATTRIBUTION"], flags=[], notes=AMBIG_NOTE)
                ev_["slots"]["DE"]["reconciliation"] = "AMBIGUOUS_ATTRIBUTION"
                ev_.pop("flags")
            else:
                ev_["slots"]["DE"]["reconciliation"] = "AMBIGUOUS_ATTRIBUTION"
    for cid, evs in oracle_entries(cases).items():
        o["cases"].append(dict(caseId=cid, evaluations=evs))
    return o


# ----------------------------------------------------------- transition ----
def _walk(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                yield (f"{path}/{k}", "<absent>", b[k])
            elif k not in b:
                yield (f"{path}/{k}", a[k], "<absent>")
            else:
                yield from _walk(a[k], b[k], f"{path}/{k}")
    elif a != b:
        yield (path, a, b)


def build_transition(v1, v2, cases):
    changed, unchanged = [], 0
    v1i = {(c["caseId"], e["policyId"], i): e for c in v1["cases"] for i, e in enumerate(c["evaluations"])}
    v2i = {(c["caseId"], e["policyId"], i): e for c in v2["cases"] for i, e in enumerate(c["evaluations"])}
    added = []
    for k, e in v2i.items():
        if k not in v1i:
            added.append(dict(caseId=k[0], policyId=k[1], finding=e["evidenceFinding"],
                              action=e["operationalAction"], reasonCodes=e["reasonCodes"]))
        elif v1i[k] == e:
            unchanged += 1
        else:
            decision = any(f[0] in ("/evidenceFinding", "/operationalAction", "/reviewRequired")
                           for f in _walk(v1i[k], e))
            changed.append(dict(caseId=k[0], policyId=k[1], decisionId=e["decisionId"],
                                kind="DECISION_CHANGE" if decision else "DETAIL_ONLY_CHANGE",
                                fields=[dict(path=p, v1=a, v2=b) for p, a, b in _walk(v1i[k], e)]))
    assert not [k for k in v1i if k not in v2i], "v2 oracle dropped a v1 evaluation"
    files = {}
    for root, names in ((V1, ["oracle.json", "policies.json", "README.md", "validate.py", "build_fixtures.py"]),):
        for n in names:
            files[f"v1/{n}"] = sha(os.path.join(root, n))
    for p in sorted(glob.glob(os.path.join(V1, "cases", "*.json"))):
        files[f"v1/cases/{os.path.basename(p)}"] = sha(p)
    return dict(
        transition="oracle v1 -> oracle v2",
        v1=dict(frozenAtCommit="72be2c9 (feature/phase1-recall-engine)", files=files,
                evaluations=len(v1i), note="Unmodified. v1 stays the Phase 1 behavioral reference."),
        v2=dict(evaluations=len(v2i), unchangedFromV1=unchanged, changed=len(changed), added=len(added)),
        changedEvaluations=changed, addedEvaluations=added,
        newCases=sorted(cases),
        vocabularyAdditions=dict(
            reasonCodes=["AMBIGUOUS_SLOT_ATTRIBUTION", "REMOVAL_SLOT_LABEL_MISMATCH", "REMOVAL_SERIAL_IN_OTHER_SLOT"],
            slotReconciliation=["AMBIGUOUS_ATTRIBUTION (below CAPTURE_GAP, above INSUFFICIENT_EVIDENCE)"],
            eventTypes=["SLOT_LABEL_SCANNED", "SLOT_ACCESS_EVIDENCE"],
            assuranceLevels=["CLAIMED_SLOT", "OBSERVED_SLOT_LABEL", "CORROBORATED_SLOT"],
            coveragePolicy=["slotAttribution block (policies.json in this directory)"],
            engineConfig=["Config(slot_attribution=True)"]),
        retiredInV2=["flag KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY (replaced by reason code "
                     "AMBIGUOUS_SLOT_ATTRIBUTION when slot_attribution is on)"],
        parameters=dict(labelAssociationWindowSeconds=60,
                        status="prototype parameter, not a proven safety standard"))


def transition_md(t):
    L = ["# Oracle version transition: v1 -> v2", "",
         f"- v1 frozen at {t['v1']['frozenAtCommit']}; {t['v1']['evaluations']} evaluations, files hashed in "
         "`VERSION_TRANSITION.json` and in `../MANIFEST.sha256` (v1 files are never edited).",
         f"- v2: {t['v2']['evaluations']} evaluations = {t['v2']['unchangedFromV1']} carried over unchanged + "
         f"{t['v2']['changed']} changed + {t['v2']['added']} added.", "",
         "## Changed evaluations", ""]
    for c in t["changedEvaluations"]:
        L.append(f"### {c['caseId']} {c['policyId']} ({c['kind']})")
        for f in c["fields"]:
            L.append(f"- `{f['path']}`: `{json.dumps(f['v1'])}` -> `{json.dumps(f['v2'])}`")
        L.append("")
    L += ["## Added evaluations", "", "| Case | Policy | Finding | Action | Reasons |", "|---|---|---|---|---|"]
    for a in t["addedEvaluations"]:
        L.append(f"| {a['caseId']} | {a['policyId'][-2:]} | {a['finding']} | {a['action']} | "
                 f"{', '.join(a['reasonCodes'])} |")
    L += ["", "## Vocabulary and parameters added", "", "```json",
          json.dumps(dict(vocabulary=t["vocabularyAdditions"], retired=t["retiredInV2"],
                          parameters=t["parameters"]), indent=2), "```", "",
          "The only decision that changed is case-06 / P1: EXCLUDED/RELEASE_ELIGIBLE (documented known-wrong "
          "in v1) -> UNRESOLVED/RECALL_HOLD. A v2 engine disagreeing with that v1 expectation is the intended "
          "safety improvement, not a regression.", ""]
    return "\n".join(L)


def main():
    cases = build_cases()
    for cid, c in cases.items():
        dump(os.path.join(HERE, "cases", f"{cid}.json"), c)
    dump(os.path.join(HERE, "policies.json"), build_policies())
    v1 = load(os.path.join(V1, "oracle.json"))
    v2 = build_oracle(cases)
    dump(os.path.join(HERE, "oracle-v2.json"), v2)
    truth = {"note": "Synthetic ground truth for cases whose original file carries none. case-06 keeps its "
                     "inline groundTruth block (v1 file, unchanged). Used by the harness only.",
             "truths": {"case-06b": {"trueP1Finding": "AFFECTED", "basis": "v1 case description: QA "
                                     "observed BR-204 still in DE"}}}
    for cid, c in cases.items():
        truth["truths"][cid] = {"trueP1Finding": c["groundTruth"]["trueP1Finding"],
                                "basis": "v2 synthetic: " + c["groundTruth"]["note"]}
    dump(os.path.join(HERE, "ground-truth.json"), truth)
    t = build_transition(v1, v2, cases)
    dump(os.path.join(HERE, "VERSION_TRANSITION.json"), t)
    with open(os.path.join(HERE, "VERSION_TRANSITION.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(transition_md(t))
    lines = [f"{sha(p)} *./{os.path.relpath(p, HERE).replace(os.sep, '/')}"
             for p in sorted(glob.glob(os.path.join(HERE, "cases", "*.json"))) +
             [os.path.join(HERE, n) for n in ("policies.json", "oracle-v2.json", "ground-truth.json",
                                              "VERSION_TRANSITION.json", "VERSION_TRANSITION.md")]]
    with open(os.path.join(HERE, "MANIFEST.sha256"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(t["v2"]))


if __name__ == "__main__":
    main()
