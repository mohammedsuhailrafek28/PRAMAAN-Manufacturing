"""Authored synthetic inputs ONLY. Physical ground truth lives in reporting code.

Never imported by the ledger, adapter, bridge or engine. Source sequences below
belong to these newly authored motor-scoped streams, not rewritten factory data.
"""
import copy
from datetime import datetime, timedelta
import hashlib
import json

from pramaan_integration import Ledger, encode_document


class Scenario:
    def __init__(self, motor="M-DEMO", *, same_lot=False, baseline=True, label=False, access=False):
        self.motor, self.events, self.seq = motor, [], {}
        self.sources = {role: f"{role}:{motor}" for role in ("MES", "ASSY", "REWORK", "QA", "HANDHELD")}
        self.actors = {"MES": "SYSTEM", "ASSY": "BUILDER", "REWORK": "REWORKER", "QA": "INDEPENDENT-QA", "HANDHELD": "OBSERVER"}
        self.sessions = [dict(sessionId=f"session:{source}", sourceId=source,
                              **{"from": "2026-08-01T00:00:00Z", "to": "2026-10-31T23:59:59Z"}, authenticated=True)
                         for source in self.sources.values()]
        self.coverage = dict(coveragePolicyId="PHASE2-COVERAGE/1", mandatoryCapture=[
            dict(operation="COMPONENT_INSTALLED", sources=[self.sources["ASSY"], self.sources["REWORK"]]),
            dict(operation="COMPONENT_REMOVED", sources=[self.sources["REWORK"]]),
            dict(operation="WORK_ORDER_*", sources=[self.sources["MES"]])],
            trustedVerifierSources=[self.sources["QA"]], slotAttribution=dict(
                version=3, unknownSlotIsCandidate=True, labelAssociationWindowSeconds=60,
                slotLabels=[dict(labelId=f"LABEL:{motor}:{slot}", motorSerial=motor, slot=slot,
                                 status="ACTIVE", provisionedAt="2026-08-01T00:00:00Z", revokedAt=None)
                            for slot in ("DE", "NDE")], labelScanSources=[self.sources["REWORK"]],
                approvedVerificationMethods=["LOT_LABEL_AND_MARKING_VISUAL", "SERIAL_MARKING_VISUAL"],
                authorizedVerifierActors=["INDEPENDENT-QA"], accessEvidenceSources=[self.sources["QA"]],
                approvedAccessMethods=["STATION_FIXTURE_RECORD"], observationClockSkewSeconds=300,
                trustedTimeSources=["DEVICE_SYNCED"]))
        self.policy = dict(policyId="RECALL-DEMO/P1", recallId="RECALL-DEMO", version=1,
                           announcedAt="2026-10-01T00:00:00Z", affectedPart="BEARING-6205",
                           affectedLots=["LOT-AFFECTED", "LOT-CORRECTED"], affectedSlots=["DE"],
                           exposureBasis="CURRENT_INSTALLATION", damageInspection=None)
        if baseline:
            self.event("WORK_ORDER_OPENED", "MES", "2026-08-01T08:00:00Z", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), wo="BUILD")
            self.original = self.event("COMPONENT_INSTALLED", "ASSY", "2026-08-01T08:01:00Z", self.part("DE", "LOT-AFFECTED"), wo="BUILD")
            self.event("COMPONENT_INSTALLED", "ASSY", "2026-08-01T08:02:00Z", self.part("NDE", "LOT-AFFECTED" if same_lot else "LOT-NDE"), wo="BUILD")
            self.event("WORK_ORDER_CLOSED", "MES", "2026-08-01T08:03:00Z", dict(disposition="COMPLETED"), wo="BUILD")
        self.event("WORK_ORDER_OPENED", "MES", "2026-09-01T08:00:00Z", dict(orderType="REWORK", expectedChanges=[dict(slot="DE", action="REPLACE" if baseline else "INSTALL")]), wo="REWORK")
        if access:
            self.event("SLOT_ACCESS_EVIDENCE", "QA", "2026-09-01T08:00:30Z", dict(method="STATION_FIXTURE_RECORD", accessibleSlots=["DE"]), wo="REWORK")
        if label:
            self.event("SLOT_LABEL_SCANNED", "REWORK", "2026-09-01T08:00:45Z", dict(labelId=f"LABEL:{motor}:DE"), wo="REWORK")
        if baseline:
            self.event("COMPONENT_REMOVED", "REWORK", "2026-09-01T08:01:00Z", dict(componentType="BEARING", slot="DE", observedPart="BEARING-6205", observedLot="LOT-AFFECTED", identityGranularity="LOT", endsInstallEventId=self.original["eventId"]), wo="REWORK")
        self.replacement = self.event("COMPONENT_INSTALLED", "REWORK", "2026-09-01T08:02:00Z", self.part("DE", "LOT-SAFE"), wo="REWORK")
        self.event("WORK_ORDER_CLOSED", "MES", "2026-09-01T08:03:00Z", dict(disposition="COMPLETED"), wo="REWORK")

    @staticmethod
    def part(slot, lot):
        return dict(componentType="BEARING", slot=slot, part="BEARING-6205", lot=lot, identityGranularity="LOT")

    def event(self, kind, source, occurred, payload, wo=None, recorded=None, supersedes=None, actor=None, refs=None):
        source_id = self.sources[source]
        self.seq[source_id] = self.seq.get(source_id, 0) + 1
        event = dict(eventId=f"urn:pramaan:{self.motor}:e{len(self.events) + 1}", eventType=kind,
                     schemaVersion=1, sourceId=source_id, sourceSeq=self.seq[source_id], motorSerial=self.motor,
                     workOrderId=wo, recallId=None, occurredAt=occurred, recordedAt=recorded or
                     (datetime.strptime(occurred, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     timeSource="DEVICE_SYNCED", actorId=actor or self.actors[source], evidenceRefs=refs or [f"scan:{self.motor}:{len(self.events)+1}"],
                     supersedesEventId=supersedes, captureSessionId=f"session:{source_id}", payload=payload)
        self.events.append(event)
        return event

    def verify(self, *, trusted=True, lot="LOT-SAFE", actor=None, at="2026-09-01T09:00:00Z", **metadata):
        return self.event("SLOT_STATE_VERIFIED", "QA" if trusted else "HANDHELD", at,
                          dict(componentType="BEARING", slot="DE", observedPart="BEARING-6205", observedLot=lot,
                               identityGranularity="LOT", method="LOT_LABEL_AND_MARKING_VISUAL", **metadata), actor=actor)

    def correction(self):
        payload = copy.deepcopy(self.replacement["payload"]); payload["lot"] = "LOT-CORRECTED"
        return self.event("COMPONENT_INSTALLED", "REWORK", self.replacement["occurredAt"], payload,
                          wo="REWORK", recorded="2026-10-02T10:00:00Z", supersedes=self.replacement["eventId"])

    def gap(self):
        assy = self.sources["ASSY"]
        session = next(s for s in self.sessions if s["sourceId"] == assy)
        session["to"] = "2026-08-01T08:03:00Z"
        self.sessions.append(dict(sessionId=f"session-later:{assy}", sourceId=assy,
                                 **{"from": "2026-08-01T09:00:00Z", "to": "2026-10-31T23:59:59Z"}, authenticated=True))

    def provision(self, ledger):
        kinds = {"MES": ["WORK_ORDER_OPENED", "WORK_ORDER_CLOSED", "CAPTURE_EXCEPTION_RAISED", "CAPTURE_EXCEPTION_RESOLVED"],
                 "ASSY": ["COMPONENT_INSTALLED"], "REWORK": ["COMPONENT_INSTALLED", "COMPONENT_REMOVED", "SLOT_LABEL_SCANNED"],
                 "QA": ["SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE", "INSPECTION_RECORDED"], "HANDHELD": ["SLOT_STATE_VERIFIED"]}
        sources = {sid: dict(streamScope="MOTOR", actors=[self.actors[role]], eventTypes=kinds[role]) for role, sid in self.sources.items()}
        ledger.register_motor(self.motor, sources=sources, sessions=self.sessions, coverage=self.coverage)

    def ingest(self, ledger, events=None):
        for event in self.events if events is None else events:
            raw = json.dumps(encode_document([event], "2026-10-21T10:00:00Z"), separators=(",", ":")).encode()
            ledger.capture(self.motor, raw, producer_source=event["sourceId"], expected_sha256=hashlib.sha256(raw).hexdigest())

    def native_case(self):
        return dict(caseId=self.motor, captureCoverage=dict(coveragePolicy=self.coverage["coveragePolicyId"], sessions=self.sessions), events=copy.deepcopy(self.events))


def populated(scenario, path=":memory:"):
    ledger = Ledger(path)
    scenario.provision(ledger); scenario.ingest(ledger)
    return ledger
