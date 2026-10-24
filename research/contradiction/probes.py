"""Assumption-violation probes. These are NOT part of the 18-fleet metrics: each one breaks a declared B1 assumption on purpose to show
what the detector does when the world is not as it assumes. `physical` is the author's statement of what really happened."""
import baseline
import candidate as B1
import fleet as FL


def probes():
    X = "SUP-X"
    out = []
    # P1: the supplier re-issued a serial number (A1 violated): two distinct bearings, same (supplier, serial)
    ev = FL.build("P1", "M101", "08-12", (FL.AFF, "SN-5001", X)) + FL.build("P1", "M102", "08-13", (FL.OK, "SN-5001", X))
    out.append((FL.fleet("P1", "Supplier re-issued a serial number", "", ev, [], [], []), "A1",
                "two physically distinct bearings share (supplier, serial); no contradiction exists", []))
    # P2: the supplier relabelled a lot (A3 violated): BR-204 and BR-204A are the same lot
    ev = FL.build("P2", "M101", "08-12", (FL.AFF, "SN-5002", X)) + FL.rework("P2", "M101", "09-10", "P2-M101-DE", ("BR-204A", "SN-5002", X), (FL.OK2, "SN-6002", X))
    out.append((FL.fleet("P2", "Lot relabelled by the supplier", "", ev, [], [], []), "A3",
                "BR-204 and BR-204A are one lot under an alias table the records do not contain; no contradiction exists", []))
    # P3: a removal really happened but was never recorded, although capture coverage is claimed complete (A4 violated)
    ev = FL.build("P3", "M101", "08-12", (FL.AFF, "SN-5003", X)) + FL.build("P3", "M102", "08-20", (FL.AFF, "SN-5003", X))
    out.append((FL.fleet("P3", "Removal done on paper only", "", ev, [], [], []), "A4",
                "the bearing was removed from M101 on a paper form that was never entered; no physical contradiction exists", []))
    # P4: a device clock is wrong by more than the declared skew (A5 violated): the removal really happened AFTER the next install
    ev = (FL.build("P4", "M101", "08-12", (FL.AFF, "SN-5004", X), open_at="07:30:00", de_at="08:00:00", close_at="08:30:00")
          + FL.rework("P4", "M101", "08-12", "P4-M101-DE", (FL.AFF, "SN-5004", X), None, at="10:00:00", open_at="09:30:00", close_at="10:30:00")
          + FL.build("P4", "M102", "08-12", (FL.AFF, "SN-5004", X), open_at="10:10:00", de_at="10:20:00", close_at="10:40:00"))
    out.append((FL.fleet("P4", "Device clock wrong by 40 minutes", "", ev, [], [], []), "A5",
                "the M101 removal device ran 40 minutes slow; the removal really happened at 10:40, after the M102 install: a real contradiction", ["real overlap"]))
    return out


def run():
    rows = []
    for f, assumption, physical, real in probes():
        found = B1.detect(f)
        b0 = baseline.b0(f)
        verdict = ("FALSE_NEGATIVE" if real and not found else "CORRECT" if real else "FALSE_POSITIVE" if found else "CORRECT")
        rows.append(dict(id=f["id"], title=f["title"], violatedAssumption=assumption, physical=physical, b1=[(c["kind"], c["cls"]) for c in found],
                         b0=[g["check"] for g in b0], b1Verdict=verdict, b0Verdict=("FALSE_POSITIVE" if b0 and not real else "FALSE_NEGATIVE" if real and not b0 else "CORRECT")))
    return rows
