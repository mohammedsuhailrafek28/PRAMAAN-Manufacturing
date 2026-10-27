"""Deterministic SYNTHETIC exports from five systems (ERP, MES, SCADA, quality, logistics) with deliberate defects.
Run: python -B -m application.dataintegration.samples.generate [outdir]   (default: this directory). Nothing here is real plant data.

Batch 1 (first day): eight assembled motors, some clean, some carrying one defect each, plus malformed rows.
Batch 2 (later): the missing ERP record for one motor, a rework of another, a re-sent batch-1 file and a record re-sent with changed content.
"""
import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
U = timezone.utc


def at(day, hh, mm, ss=0):
    return datetime(2026, 10, day, hh, mm, ss, tzinfo=U)


def erp_ts(d):
    return d.astimezone(IST).strftime("%d.%m.%Y %H:%M:%S")


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def csv_text(header, rows, delimiter):
    out = io.StringIO()
    w = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return out.getvalue()


ERP_H = ["BELNR", "POSNR", "MOTOR_NO", "POSITION", "BEARING_LOT", "BEARING_SERIAL", "STEEL_LOT", "VENDOR_ID", "VENDOR_NAME", "ISSUE_TS"]
MES_H = ["EVENT_ID", "MOTOR_SERIAL", "EVENT_TIME", "EVENT_CODE", "ORDER_NO", "ORDER_TYPE", "SLOTS", "SLOT", "LOT", "SERIAL", "DISPOSITION", "STATION", "OPERATOR"]
QC_H = ["INSPECTION_NO", "MOTOR", "INSPECTED_AT", "PROTOCOL", "OUTCOME", "INSPECTOR", "QUALIFIED_FOR", "POSITION", "LOT"]
SUPPLIER = {"BR-204": ("STEEL-26-410", "SUP-NSB-01", "Northstar Bearings — synthetic supplier"),
            "BR-310": ("STEEL-26-518", "SUP-KAV-02", "Kaveri Precision — synthetic supplier"),
            "BR-312": ("STEEL-26-518", "SUP-KAV-02", "Kaveri Precision — synthetic supplier")}


class Feed:
    def __init__(self):
        self.erp, self.mes, self.qc, self.scada, self.ship = [], [], [], [], []
        self._doc, self._mes, self._qc, self._sample = 4500000, 100, 700, 0

    def issue(self, motor, slot, lot, when, serial="", doc=None, motor_text=None, raw_lot=None, ts_text=None):
        steel, vid, vname = SUPPLIER.get(lot, ("STEEL-26-999", "SUP-X-09", "Unlisted supplier"))
        if doc is None:
            self._doc += 1
            doc = self._doc
        self.erp.append([str(doc), "10" if slot == "DE" else "20", motor_text or motor, slot, raw_lot or lot, serial, steel, vid, vname, ts_text or erp_ts(when)])

    def mes_row(self, motor, when, code, order, otype="", slots="", slot="", lot="", serial="", disp="", station="ASSY-01", op="OP-17", eid=None, motor_text=None):
        if eid is None:
            self._mes += 1
            eid = f"MES-{self._mes:06d}"
        self.mes.append([eid, motor_text or motor, iso(when), code, order, otype, slots, slot, lot, serial, disp, station, op])
        return eid

    def build(self, motor, order, t0, de, nde, de_serial="", nde_serial="", close=True):
        """OPEN, two INSTALL rows and (optionally) CLOSE, five minutes apart starting at t0."""
        self.mes_row(motor, t0, "OPEN", order, "BUILD", "DE;NDE")
        self.mes_row(motor, t0 + timedelta(minutes=5), "INSTALL", order, slot="DE", lot=de, serial=de_serial)
        self.mes_row(motor, t0 + timedelta(minutes=10), "INSTALL", order, slot="NDE", lot=nde, serial=nde_serial)
        if close:
            self.mes_row(motor, t0 + timedelta(minutes=15), "CLOSE", order, disp="COMPLETED")

    def inspect(self, motor, when, result, qid=None, lot="", slot=""):
        if qid is None:
            self._qc += 1
            qid = f"QI-{self._qc:05d}"
        self.qc.append([qid, motor, when.astimezone(IST).strftime("%Y-%m-%d %H:%M"), "QP-BEARING-FIT-3", result, "QA-INS-02", "DIMENSIONAL;FIT", slot, lot])

    def sample(self, when, tag, value, unit, motor="", order="", station="PRESS-01", quality="GOOD", sid=None):
        if sid is None:
            self._sample += 1
            sid = f"S-{self._sample:05d}"
        self.scada.append({"sampleId": sid, "ts": iso(when), "asset": {"station": station, "motor": motor, "order": order},
                           "measurement": {"tag": tag, "value": value, "unit": unit, "quality": quality}})

    def ship_row(self, motor, shipment, when, customer="Aster Pump Systems — synthetic customer", dest="Coimbatore distribution centre"):
        self.ship.append({"shipment": {"id": shipment, "dispatchedAt": when.astimezone(IST).isoformat()}, "unit": {"serial": motor},
                          "consignee": {"name": customer, "destination": dest}, "carrier": {"name": "Synthetic Freight Co", "tracking": "TRK-" + shipment[4:]}})


def batch1() -> Feed:
    f = Feed()
    # 27001 clean, serial-tracked, full evidence
    f.issue("MTR-27001", "DE", "BR-204", at(1, 3, 30), "BRG-27001-DE-01"); f.issue("MTR-27001", "NDE", "BR-310", at(1, 3, 31), "BRG-27001-NDE-01")
    f.build("MTR-27001", "WO-5001", at(1, 5, 0), "BR-204", "BR-310", "BRG-27001-DE-01", "BRG-27001-NDE-01")
    f.inspect("MTR-27001", at(1, 6, 0), "OK"); f.ship_row("MTR-27001", "SHP-9001", at(2, 4, 0))
    f.sample(at(1, 5, 6), "PRESS_FORCE_KN", 18.4, "kN", motor="MTR-27001", order="WO-5001")
    f.sample(at(1, 5, 7), "TORQUE_NM", "112,5", "N.m", order="WO-5001")                      # no motor: resolved through the MES work order; decimal comma
    f.sample(at(1, 5, 11), "BEARING_TEMP_C", 41.2, "degC", motor="MTR-27001", order="WO-5001")
    # 27002 declared registry alias (NSB-204 = BR-204), lot-level identity for the NDE bearing
    f.issue("MTR-27002", "DE", "BR-204", at(1, 4, 0), "", raw_lot="NSB-204"); f.issue("MTR-27002", "NDE", "BR-312", at(1, 4, 1))
    f.build("MTR-27002", "WO-5002", at(1, 6, 0), "NSB-204", "BR-312")
    f.ship_row("MTR-27002", "SHP-9002", at(2, 4, 30))
    # 27003 contradiction: ERP issued BR-310 to DE but MES installed BR-312
    f.issue("MTR-27003", "DE", "BR-310", at(1, 4, 5), "BRG-27003-DE-01"); f.issue("MTR-27003", "NDE", "BR-312", at(1, 4, 6), "BRG-27003-NDE-01")
    f.build("MTR-27003", "WO-5003", at(1, 7, 0), "BR-312", "BR-312", "BRG-27003-DE-01", "BRG-27003-NDE-01")
    f.ship_row("MTR-27003", "SHP-9003", at(2, 5, 0))
    # 27004 lot not in the registry (ERP and MES agree on it)
    f.issue("MTR-27004", "DE", "XB-999", at(1, 4, 10)); f.issue("MTR-27004", "NDE", "BR-310", at(1, 4, 11))
    f.build("MTR-27004", "WO-5004", at(1, 8, 0), "XB-999", "BR-310")
    # 27005 NDE install has no ERP issue (supplied in batch 2)
    f.issue("MTR-27005", "DE", "BR-310", at(1, 4, 15))
    f.build("MTR-27005", "WO-5005", at(1, 9, 0), "BR-310", "BR-312")
    f.ship_row("MTR-27005", "SHP-9010", at(2, 5, 30))                                         # same shipment id as 27006 below, different motor
    # 27006 duplicates: exact repeat of an ERP row, a conflicting repeat of another, exact repeat of an MES row
    f.issue("MTR-27006", "DE", "BR-310", at(1, 4, 20), doc=4500101); f.issue("MTR-27006", "DE", "BR-310", at(1, 4, 20), doc=4500101)
    f.issue("MTR-27006", "NDE", "BR-312", at(1, 4, 21), doc=4500102); f.issue("MTR-27006", "NDE", "BR-310", at(1, 4, 21), doc=4500102)
    f.build("MTR-27006", "WO-5006", at(1, 10, 0), "BR-310", "BR-312")
    f.mes.append(list(f.mes[-2]))
    f.ship_row("MTR-27006", "SHP-9010", at(2, 6, 0))
    # 27007 shipped before the build order was closed
    f.issue("MTR-27007", "DE", "BR-312", at(1, 5, 0)); f.issue("MTR-27007", "NDE", "BR-312", at(1, 5, 1))
    f.build("MTR-27007", "WO-5007", at(1, 11, 0), "BR-312", "BR-312")
    f.ship_row("MTR-27007", "SHP-9007", at(1, 11, 7))
    # 27008 recorded FAIL on the DE bearing, shipped afterwards with no later PASS
    f.issue("MTR-27008", "DE", "BR-204", at(1, 5, 5), "BRG-27008-DE-01"); f.issue("MTR-27008", "NDE", "BR-310", at(1, 5, 6), "BRG-27008-NDE-01")
    f.build("MTR-27008", "WO-5008", at(1, 12, 0), "BR-204", "BR-310", "BRG-27008-DE-01", "BRG-27008-NDE-01")
    f.inspect("MTR-27008", at(1, 12, 30), "NOK", lot="BR-204", slot="DE"); f.ship_row("MTR-27008", "SHP-9008", at(2, 7, 0))
    # an ERP-only motor written with a space instead of a dash (normalised), and a motor no other system knows
    f.issue("MTR-27009", "DE", "BR-310", at(1, 5, 10), motor_text="mtr 27009")
    # a look-alike spelling is never normalised into a registered lot
    f.issue("MTR-27013", "DE", "BR-310", at(1, 5, 12), raw_lot="br-310 ")
    # defects that are rejected outright
    f.issue("MTR-27010", "DE", "BR-310", at(1, 5, 11), ts_text="31.02.2026 10:00:00")        # impossible calendar date
    f.mes_row("", at(1, 13, 0), "OPEN", "WO-5099", "BUILD", "DE;NDE")                          # no motor
    f.mes_row("MTR-27011", at(1, 13, 1), "PAUSE", "WO-5098")                                   # unmapped event code
    f.mes.append(["MES-000900", "MTR-27012", "2026-10-01T13:02:00Z", "OPEN"])                  # ragged row: too few cells
    # more SCADA / quality / logistics edge cases
    f.sample(at(1, 5, 8), "PRESS_FORCE_KN", 9999, "kN", motor="MTR-27001", order="WO-5001")  # implausible
    f.sample(at(1, 5, 9), "TORQUE_NM", 100, "N.m", motor="MTR-27001", order="WO-5001", quality="BAD")
    f.sample(at(1, 5, 10), "TORQUE_NM", 101, "N.m", order="WO-NOSUCH")                        # cannot be tied to a motor
    f.sample(at(1, 23, 30), "BEARING_TEMP_C", 40.0, "degC", motor="MTR-27001", order="WO-5001")  # long after the order closed
    f.inspect("MTR-29999", at(1, 6, 30), "PASS")                                              # unknown motor
    return f


def batch2() -> Feed:
    """New records, plus one batch-1 MES record re-sent with changed content. The unchanged batch-1 files are re-imported as they are."""
    new = Feed()
    new._doc, new._mes = 4500200, 400
    new.issue("MTR-27005", "NDE", "BR-312", at(1, 4, 16))                                    # the missing upstream record for 27005
    new.issue("MTR-27001", "DE", "BR-312", at(3, 3, 0), "BRG-27001-DE-02")                  # replacement bearing for the rework below
    new.mes_row("MTR-27001", at(3, 4, 0), "OPEN", "WO-5101", "REWORK", "DE")
    new.mes_row("MTR-27001", at(3, 4, 5), "REMOVE", "WO-5101", slot="DE", lot="BR-204", serial="BRG-27001-DE-01", station="REWORK-02", op="OP-31")
    new.mes_row("MTR-27001", at(3, 4, 10), "INSTALL", "WO-5101", slot="DE", lot="BR-312", serial="BRG-27001-DE-02", station="REWORK-02", op="OP-31")
    new.mes_row("MTR-27001", at(3, 4, 15), "CLOSE", "WO-5101", disp="COMPLETED", station="REWORK-02", op="OP-31")
    # MES-000103 (batch 1: 27001 DE install) is re-sent with a different lot under the same event id
    new.mes_row("MTR-27001", at(1, 5, 5), "INSTALL", "WO-5001", slot="DE", lot="BR-310", serial="BRG-27001-DE-01", eid="MES-000102")
    return new


FILES = {"erp_lot_issue": ("csv", ";"), "mes_assembly": ("csv", ","), "scada_signals": ("json", None), "quality_inspections": ("csv", "\t"), "logistics_dispatch": ("json", None)}


def render(feed: Feed) -> dict[str, str]:
    return {"erp_lot_issue.csv": csv_text(ERP_H, feed.erp, ";"), "mes_assembly.csv": csv_text(MES_H, feed.mes, ","),
            "quality_inspections.tsv": csv_text(QC_H, feed.qc, "\t"),
            "scada_signals.json": json.dumps({"exportedFrom": "synthetic-historian", "samples": feed.scada}, indent=1, ensure_ascii=False) + "\n",
            "logistics_dispatch.json": json.dumps({"exportedFrom": "synthetic-tms", "shipments": feed.ship}, indent=1, ensure_ascii=False) + "\n"}


def generate() -> dict[str, dict[str, str]]:
    r2 = render(batch2())
    return {"batch1": render(batch1()), "batch2": {k: v for k, v in r2.items() if k in ("erp_lot_issue.csv", "mes_assembly.csv")}}


def main(out=None):
    base = Path(out) if out else Path(__file__).parent
    for batch, files in generate().items():
        (base / batch).mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (base / batch / name).write_text(text, encoding="utf-8", newline="")
            print(batch, name, len(text))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
