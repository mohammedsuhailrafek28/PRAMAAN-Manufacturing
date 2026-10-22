"""Independent adversarial audit of H1/H2 Option A. READ-ONLY with respect to the audited tree:
every scenario runs on disposable temp databases. Imports the audited modules without modifying them.

Run:  <venv python> adversarial_audit.py <repo_root> <results.json>
Each scenario RECORDS expected vs observed; it does not assert, so every deviation is reported.
"""
import copy, json, os, sqlite3, sys, tempfile, threading, time, traceback, subprocess
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "integration"))
from application.service import Manufacturing
from application.anchors import (export_anchor, export_v1, verify_anchor, TrustedAnchor, publish_candidate, FORMAT_V2)
from application.audit import IntegrityFailure, Verifying
from application.server import make_server
from pramaan_integration.profile import digest

RESULTS = []


def rec(id, title, expected, observed, ok):
    RESULTS.append(dict(id=id, title=title, expected=expected, observed=observed, verdict="PASS" if ok is True else "FAIL" if ok is False else str(ok)))
    print(f"[{RESULTS[-1]['verdict']:7}] {id}: {title}\n          expected: {expected}\n          observed: {observed}", flush=True)


def attempt(fn):
    """Return ('ok', value) or ('raise', code-or-type)."""
    try:
        return "ok", fn()
    except IntegrityFailure as e:
        return "raise", e.code
    except Exception as e:  # noqa
        return "raise", f"{type(e).__name__}"


class World:
    def __init__(self, motors=("MTR-AAA1", "MTR-AAA2")):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / "ledger.sqlite"
        self.app = Manufacturing(self.path)
        a = self.app
        a.create_unit("MTR-AAA1"); a.assemble("MTR-AAA1", "BR-204", "BR-310")      # affected (DE)
        a.create_unit("MTR-AAA2"); a.assemble("MTR-AAA2", "BR-310", "BR-312")      # excluded with evidence
        a.announce("BR-204", ["DE"]); a.snapshot()
        self.c0 = export_anchor(a)
        self.c0_file = self.dir / "c0.json"; publish_candidate(self.c0_file, self.c0)

    def backup(self):
        db = sqlite3.connect(":memory:"); self.app.db.backup(db); return db

    def reopen(self):
        self.app.close(); self.app = Manufacturing(self.path)

    def snap(self, trusted=None):
        return self.app.snapshot(trusted_anchor=trusted)

    def close(self):
        try: self.app.close()
        finally: self.tmp.cleanup()


def rehash_journal(db):
    previous = "GENESIS"
    db.execute("DROP TRIGGER IF EXISTS app_audit_no_update")
    for row in db.execute("SELECT * FROM app_audit ORDER BY seq").fetchall():
        h = digest(dict(seq=row["seq"], kind=row["kind"], payload=json.loads(row["payload"]), previous=previous))
        db.execute("UPDATE app_audit SET previous=?,hash=? WHERE seq=?", (previous, h, row["seq"]))
        previous = h
    db.execute("UPDATE app_audit_head SET hash=?,count=(SELECT COUNT(*) FROM app_audit) WHERE id=1", (previous,))
    db.commit()


# ---------------------------------------------------------------------------------------------- R-matrix
def r_matrix():
    # R1: in-process rollback after extension verified; also rollback to BEFORE the checkpoint
    w = World()
    try:
        old = w.backup(); t = TrustedAnchor(w.c0_file)
        w.snap(t); w.app.observe("MTR-AAA2", "BR-204"); s1 = w.snap(t)
        old.backup(w.app.db)
        r = attempt(lambda: w.snap(t))
        rec("R1", "in-process rollback to exact-checkpoint state after a verified extension", "ANCHOR_INVALID / ROLLBACK_DETECTED", f"first={s1['checkpoint']['state']}, then {r}", r == ("raise", "ROLLBACK_DETECTED"))
    finally: w.close()

    w = World()
    try:
        t = TrustedAnchor(w.c0_file); w.snap(t)
        # rollback to a state OLDER than the checkpoint: build older db by taking a backup of a world before announcing is not possible here;
        # emulate by restoring a backup taken before the extension but using a high-water set by a later verify
        w.app.observe("MTR-AAA1", "BR-204"); w.snap(); mid = w.backup(); w.app.observe("MTR-AAA2", "BR-204"); w.snap(t)
        mid.backup(w.app.db)
        r = attempt(lambda: w.snap(t))
        rec("R1b", "in-process rollback to an intermediate head (between checkpoint and last verified head)", "ROLLBACK_DETECTED", str(r), r == ("raise", "ROLLBACK_DETECTED"))
    finally: w.close()

    # R2: restart with newer checkpoint against older archive
    w = World()
    try:
        old = w.backup(); w.app.observe("MTR-AAA2", "BR-204"); w.snap(); c1 = export_anchor(w.app)
        old.backup(w.app.db)
        r = attempt(lambda: verify_anchor(w.app, c1))
        rec("R2", "restart with newest checkpoint, older archive", "ANCHOR_INVALID / PREFIX_MISMATCH", str(r), r == ("raise", "PREFIX_MISMATCH"))
    finally: w.close()

    # R3: restart with older checkpoint, intermediate archive
    w = World()
    try:
        w.app.observe("MTR-AAA1", "BR-310"); w.snap(); inter = w.backup()
        t = TrustedAnchor(w.c0_file); w.app.observe("MTR-AAA2", "BR-204"); w.snap(t)
        inter.backup(w.app.db); w.reopen()
        s = w.snap(TrustedAnchor(w.c0_file))
        rec("R3", "after restart: older checkpoint + intermediate archive", "ANCHORED_PREFIX_ONLY, eligibility withheld", f"{s['checkpoint']['state']} elig={[v['currentReleaseEligible'] for v in s['eligibility'].values()]}",
            s["checkpoint"]["state"] == "ANCHORED_PREFIX_ONLY" and not any(v["currentReleaseEligible"] for v in s["eligibility"].values()))
    finally: w.close()

    # R4: exact checkpoint rollback after restart (documented residual)
    w = World()
    try:
        old = w.backup(); w.app.observe("MTR-AAA2", "BR-204"); w.snap()
        old.backup(w.app.db); w.reopen()
        s = w.snap(TrustedAnchor(w.c0_file))
        rec("R4", "after restart: archive rolled back to EXACTLY the trusted checkpoint", "ANCHORED_CURRENT (declared undetectable residual; must not be claimed detected)", s["checkpoint"]["state"], s["checkpoint"]["state"] == "ANCHORED_CURRENT")
    finally: w.close()

    # R5 / R10
    w = World()
    try:
        w.app.observe("MTR-AAA2", "BR-204")  # event appended, not evaluated
        r10 = verify_anchor(w.app, w.c0)["state"]
        s = w.snap(TrustedAnchor(w.c0_file))
        a2 = next(iter(s["decisions"]["MTR-AAA2"].values()))["current"]
        rec("R10", "ledger event appended, not yet evaluated", "ANCHORED_PREFIX_ONLY", r10, r10 == "ANCHORED_PREFIX_ONLY")
        rec("R5", "legitimate capture after checkpoint", "PREFIX_ONLY, eligibility withheld for ALL motors, holds visible, checkpointRequired",
            f"{s['checkpoint']['state']} required={s['checkpoint']['checkpointRequired']} elig={ {k:v['currentReleaseEligible'] for k,v in s['eligibility'].items()} } A2action={a2['operationalAction']} freshness={s['freshness']['status']}",
            s["checkpoint"]["state"] == "ANCHORED_PREFIX_ONLY" and s["checkpoint"]["checkpointRequired"] and not any(v["currentReleaseEligible"] for v in s["eligibility"].values()) and a2["operationalAction"] == "RECALL_HOLD")
    finally: w.close()

    # R6/R7 variants: forged evaluation, rehashed. Variants: (a) release in decision only (b) release in raw+decision (c) consistently forged raw+derived+manifest-unchanged
    for tag, mut in [("a-decision-only", lambda e: e["decision"].update(operationalAction="RELEASE_ELIGIBLE", reasonCodes=[], precautionaryHold=False)),
                     ("b-raw-and-decision", lambda e: (e["raw"].update(operationalAction="RELEASE_ELIGIBLE", evidenceFinding="EXCLUDED_WITH_EVIDENCE", reasonCodes=[]), e["decision"].update(operationalAction="RELEASE_ELIGIBLE", evidenceFinding="EXCLUDED_WITH_EVIDENCE", reasonCodes=[], precautionaryHold=False))),
                     ("c-version-bump", lambda e: e["decision"].update(version=e["decision"]["version"] + 5))]:
        w = World()
        try:
            t = TrustedAnchor(w.c0_file); t.verify(w.app)
            w.app.observe("MTR-AAA2", "BR-204"); w.snap()
            entry = copy.deepcopy([p for k, p in w.app.audit.verify() if k == "EVALUATION"][-1]); mut(entry)
            w.app.db.execute("DROP TRIGGER app_audit_no_update")
            w.app.db.execute("UPDATE app_audit SET payload=? WHERE seq=(SELECT MAX(seq) FROM app_audit)", (json.dumps(entry),))
            rehash_journal(w.app.db)
            r = attempt(lambda: t.verify(w.app))
            rec(f"R6/R7-{tag}", "forged EVALUATION with recomputed hash chain", "EXTENSION_INVALID", str(r), r == ("raise", "EXTENSION_INVALID"))
        finally: w.close()

    # R8 orphan, R9 resolved, unknown kind
    for kind, payload, code, id in [("OBLIGATION_CREATED", dict(obligationId="x", unitId="MTR-AAA2"), "EXTENSION_INVALID", "R8"),
                                    ("OBLIGATION_RESOLVED", dict(obligationId="x"), "RESOLUTION_FORBIDDEN", "R9"),
                                    ("SOMETHING_ELSE", dict(a=1), "EXTENSION_INVALID", "R-unknown-kind")]:
        w = World()
        try:
            w.app.audit.append(kind, payload); w.app.db.commit()
            r = attempt(lambda: verify_anchor(w.app, w.c0))
            rec(id, f"journal extension with {kind}", code, str(r), r == ("raise", code))
        finally: w.close()

    # R11 v1
    w = World()
    try:
        r = verify_anchor(w.app, export_v1(w.app))["state"]
        rec("R11", "v1 checkpoint over a fully current archive", "never ANCHORED_CURRENT", r, r != "ANCHORED_CURRENT")
    finally: w.close()

    # R15 chain
    w = World()
    try:
        w.app.observe("MTR-AAA2", "BR-204"); w.snap(); s1 = export_anchor(w.app, w.c0)
        r_none = attempt(lambda: verify_anchor(w.app, s1))
        r_ok = attempt(lambda: verify_anchor(w.app, s1, w.c0))
        other = export_anchor(w.app)  # unrelated root
        r_wrong = attempt(lambda: verify_anchor(w.app, s1, other))
        rec("R15", "successor without / with correct / with wrong previous", "PREFIX_MISMATCH / CURRENT / PREFIX_MISMATCH", f"{r_none} / {r_ok[1]['state'] if r_ok[0]=='ok' else r_ok} / {r_wrong}",
            r_none == ("raise", "PREFIX_MISMATCH") and r_ok[0] == "ok" and r_ok[1]["state"] == "ANCHORED_CURRENT" and r_wrong == ("raise", "PREFIX_MISMATCH"))
    finally: w.close()

    # R16: legacy row in the MIDDLE followed by modern publication (Codex test appends legacy at the END only)
    w = World()
    try:
        entry = copy.deepcopy(next(p for k, p in w.app.audit.verify() if k == "EVALUATION")); entry.pop("manifest")
        w.app.audit.append("EVALUATION", entry); w.app.db.commit()
        rs = attempt(lambda: (w.app.observe("MTR-AAA1", "BR-204"), w.snap()))   # new modern publication after the legacy row
        rec("R16-mid-service", "service snapshot after a legacy (manifest-less) row exists for a motor", "degrade to HISTORICAL_UNVERIFIABLE; no crash", str(rs[1]) if rs[0]=='raise' else 'ok', rs[0]=='ok')
        r = attempt(lambda: w.app.audit.verify_publications())
        rec("R16-mid", "legacy (manifest-less) row followed by modern publications of the same motor", "HISTORICAL_UNVERIFIABLE (degrade, never current)", str(r if r[0] == 'raise' else r[1]['status']),
            r[0] == "ok" and r[1]["status"] == "HISTORICAL_UNVERIFIABLE")
    finally: w.close()

    # R19
    with tempfile.TemporaryDirectory() as d:
        a = Manufacturing(Path(d) / "e.sqlite")
        try:
            before = export_anchor(a); a.announce("BR-204", ["DE"])
            r = verify_anchor(a, before)["state"]
            rec("R19", "checkpoint before policy exists; policy added later", "ANCHORED_PREFIX_ONLY", r, r == "ANCHORED_PREFIX_ONLY")
        finally: a.close()


# ---------------------------------------------------------------------------------------------- extra attacks
def x_attacks():
    # X1: derivation-consistent forged evaluation at an EARLIER watermark appended with a valid chain (host journal writer)
    w = World()
    try:
        t = TrustedAnchor(w.c0_file); w.snap(t)
        w.app.observe("MTR-AAA2", "BR-204"); w.snap()           # A2 now held (precautionary)
        recs = w.app.audit.verify()
        evals = [p for k, p in recs if k == "EVALUATION" and p["context"]["motor"] == "MTR-AAA2"]
        old = evals[0]
        # re-derive an entry for the OLD (excluded) watermark but chained AFTER the hold, via the real derivation function
        from application.audit import derive_publication
        from pramaan_integration import engine_bridge
        case, manifest = w.app.ledger.snapshot("MTR-AAA2", old["manifest"]["watermark"])
        raw = engine_bridge.pramaan_recall.evaluate(case, copy.deepcopy(old["policy"]), w.app.ledger._config("MTR-AAA2")["coverage"], manifest["watermark"], engine_bridge.Config.v3())
        archive = w.app.db.execute("SELECT archive_id FROM app_audit_head").fetchone()[0]
        obligations = w.app.audit.outstanding(recs)
        entry, created, reused = derive_publication(case, manifest, old["policy"], raw, evals, obligations, archive)
        if created: w.app.audit.append("OBLIGATION_CREATED", created)
        w.app.audit.append("EVALUATION", entry); w.app.db.commit()
        proof = attempt(lambda: w.app.audit.verify_publications())
        s = w.snap(TrustedAnchor(w.c0_file))
        a2 = next(iter(s["decisions"]["MTR-AAA2"].values()))["current"]
        rec("X1", "valid-chain, derivation-consistent evaluation of an OLD (excluded) watermark appended after a hold",
            "must not yield eligibility; ideally rejected (non-monotonic watermark)",
            f"H2={proof[1]['status'] if proof[0]=='ok' else proof}; state={s['checkpoint']['state']}; A2 current action={a2['operationalAction']} version={a2['version']}; elig={s['eligibility']['MTR-AAA2']['currentReleaseEligible']}",
            not s["eligibility"]["MTR-AAA2"]["currentReleaseEligible"])
        rec("X1-note", "H2 accepts non-monotonic per-motor watermark ordering", "reject (EXTENSION_INVALID) preferred", f"H2 result {proof[0]}", proof[0] == "raise")
    except Exception:
        rec("X1", "forged earlier-watermark evaluation", "n/a", traceback.format_exc()[-600:], "ERROR")
    finally: w.close()

    # X2: derivation-consistent forged POLICY evaluation (affectedLots empty) accepted by H2?
    w = World()
    try:
        from application.audit import derive_publication
        from pramaan_integration import engine_bridge
        recs = w.app.audit.verify()
        evals = [p for k, p in recs if k == "EVALUATION" and p["context"]["motor"] == "MTR-AAA1"]
        forged_policy = copy.deepcopy(evals[0]["policy"]); forged_policy["affectedLots"] = ["BR-NONE"]
        case, manifest = w.app.ledger.snapshot("MTR-AAA1", w.app.ledger.watermark("MTR-AAA1"))
        raw = engine_bridge.pramaan_recall.evaluate(case, copy.deepcopy(forged_policy), w.app.ledger._config("MTR-AAA1")["coverage"], manifest["watermark"], engine_bridge.Config.v3())
        archive = w.app.db.execute("SELECT archive_id FROM app_audit_head").fetchone()[0]
        entry, created, reused = derive_publication(case, manifest, forged_policy, raw, [], w.app.audit.outstanding(recs), archive)
        w.app.audit.append("EVALUATION", entry); w.app.db.commit()
        proof = attempt(lambda: w.app.audit.verify_publications())
        s = w.snap(TrustedAnchor(w.c0_file))
        rec("X2", "evaluation produced under a policy never announced (forged policy) appended with valid chain",
            "preferably rejected: entry policy must equal an announced recall_announcements policy", f"H2={proof[1]['status'] if proof[0]=='ok' else proof}; state={s['checkpoint']['state']}; A1 elig={s['eligibility']['MTR-AAA1']['currentReleaseEligible']}",
            proof[0] == "raise")
    except Exception:
        rec("X2", "forged policy evaluation", "n/a", traceback.format_exc()[-600:], "ERROR")
    finally: w.close()

    # X3: successors / forks
    w = World()
    try:
        w.app.observe("MTR-AAA2", "BR-204"); w.snap(); s1 = export_anchor(w.app, w.c0)
        w.app.observe("MTR-AAA1", "BR-310"); w.snap(); s2_skip = export_anchor(w.app, w.c0)        # skips s1
        e3 = attempt(lambda: export_anchor(w.app, s1))
        rec("X3-depth3", "export a THIRD-generation checkpoint (previous = non-root successor s1)", "succeeds (chain must be extendable beyond 2 links)", str(e3[1]) if e3[0]=='raise' else 'ok', e3[0]=='ok')
        s2_chain = e3[1] if e3[0]=='ok' else None
        cand = [("s1", s1, w.c0), ("s2-skips-s1", s2_skip, w.c0)] + ([("s2-chained", s2_chain, s1)] if s2_chain else [])
        res = {n: attempt(lambda c=c, p=p: verify_anchor(w.app, c, p)) for n, c, p in cand}
        summ = {k: (v[1]["state"] if v[0] == "ok" else v[1]) for k, v in res.items()}
        rec("X3", "multiple successors of the same predecessor / chain skipping", "equivocation cannot be detected by software; document. Observed acceptance states:", json.dumps(summ), None)
    finally: w.close()

    # X4: checkpoint field fuzz (checksum recomputed). Never CURRENT unless byte-identical semantics.
    w = World()
    try:
        base = w.c0["body"]; out = {}; bad = []
        def mutants():
            for k in base:
                if k == "format": continue
                yield k, None
                yield k, "X"
                yield k, 0
                yield k, -1
                yield k, 1.5
                yield k, True
                yield k, []
                yield k, {}
            for tbl in base["ledger"]["rows"]:
                yield f"ledger.rows.{tbl}[drop]", ("L", tbl)
                yield f"ledger.rows.{tbl}[extra]", ("E", tbl)
            yield "ledger.sourceHeads[empty]", ("H", None)
        n = 0
        for key, val in mutants():
            body = copy.deepcopy(base)
            if isinstance(val, tuple):
                kind, tbl = val
                if kind == "L": body["ledger"]["rows"][tbl] = body["ledger"]["rows"][tbl][:-1]
                elif kind == "E": body["ledger"]["rows"][tbl] = body["ledger"]["rows"][tbl] + ["0" * 64]
                else: body["ledger"]["sourceHeads"] = {}
            else:
                body[key] = val
            cp = dict(body=body, checksum=digest(body)); n += 1
            r = attempt(lambda: verify_anchor(w.app, cp))
            state = r[1]["state"] if r[0] == "ok" else r[1]
            out[key if not isinstance(val, tuple) else key] = state
            if state == "ANCHORED_CURRENT": bad.append(key)
        # "drop last row" truncations legitimately weaken a checkpoint (prefix) -> may stay PREFIX_ONLY; must not be CURRENT
        rec("X4", f"{n} checkpoint field mutations with recomputed checksum", "none yields ANCHORED_CURRENT", f"CURRENT for: {bad or 'none'}", not bad)
        rec("X4-types", "type-confusion probes (True/1.5/[]/{}) never crash with a non-code error", "only fixed codes", json.dumps(sorted({v for v in out.values()})), all(v in ("PREFIX_MISMATCH", "ANCHORED_PREFIX_ONLY", "EXTENSION_INVALID", "RESOLUTION_FORBIDDEN", "ROLLBACK_DETECTED", "CHECKPOINT_UNAVAILABLE") for v in out.values()))
    finally: w.close()

    # X5: DB mutation catalogue under a fixed trusted checkpoint, via a TrustedAnchor that is warm
    def mutate_and_check(name, mutator, expect_not_current=True):
        w = World()
        try:
            t = TrustedAnchor(w.c0_file); w.snap(t); w.snap(t)       # warm caches
            try:
                mutator(w)
            except Exception as e:
                rec(f"X5-{name}", "mutation applied", "n/a", f"mutator failed: {type(e).__name__}: {e}", "ERROR"); return
            r = attempt(lambda: w.snap(t))
            state = r[1]["checkpoint"]["state"] if r[0] == "ok" else r[1]
            not_current = state != "ANCHORED_CURRENT"
            rec(f"X5-{name}", f"warm-cache anchor, then {name}", "not ANCHORED_CURRENT" if expect_not_current else "ANCHORED_CURRENT (benign)", state, not_current == expect_not_current)
        finally: w.close()
    mutate_and_check("append_ledger_event", lambda w: w.app.observe("MTR-AAA2", "BR-204"))
    mutate_and_check("create_new_motor", lambda w: w.app.create_unit("MTR-NEW1"))
    mutate_and_check("new_recall_announcement_row", lambda w: (w.app.db.execute("INSERT INTO recall_announcements VALUES(2,?,?)", (json.dumps(dict(w.app.policy(), version=2, affectedLots=[])), digest(dict(w.app.policy(), version=2, affectedLots=[])))), w.app.db.commit()))
    def edit_received(w):
        w.app.db.execute("DROP TRIGGER captures_no_update"); w.app.db.execute("UPDATE captures SET received='2000-01-01T00:00:00Z' WHERE rowid=1"); w.app.db.commit()
    mutate_and_check("edit_captures.received_(unused_by_decisions)", edit_received)
    def edit_clock(w):
        w.app.db.execute("UPDATE app_clock SET at='2030-01-01T00:00:00Z'"); w.app.db.commit()
    mutate_and_check("edit_app_clock_(unbound_table)", edit_clock, expect_not_current=False)
    def edit_units(w):
        w.app.db.execute("UPDATE app_units SET title='x' WHERE serial='MTR-AAA1'"); w.app.db.commit()
    mutate_and_check("edit_app_units.title", edit_units)
    def drop_journal_row_rehash(w):
        w.app.db.execute("DROP TRIGGER app_audit_no_delete"); w.app.db.execute("DELETE FROM app_audit WHERE seq=(SELECT MAX(seq) FROM app_audit)"); rehash_journal(w.app.db)
    mutate_and_check("truncate_last_journal_entry_with_rehash_(in-process)", drop_journal_row_rehash)

    # X6: stale-cache reuse - same head count/hash after attacker swaps ledger row content of equal length
    w = World()
    try:
        t = TrustedAnchor(w.c0_file); w.snap(t)
        w.app.db.execute("DROP TRIGGER events_no_update")
        row = w.app.db.execute("SELECT ordinal,native FROM events ORDER BY ordinal LIMIT 1").fetchone()
        w.app.db.execute("UPDATE events SET native=? WHERE ordinal=?", (row["native"].replace("a", "b", 1) if "a" in row["native"] else row["native"] + " ", row["ordinal"])); w.app.db.commit()
        r = attempt(lambda: w.snap(t))
        rec("X6", "equal-length ledger row edit after caches are warm", "not ANCHORED_CURRENT", r[1]["checkpoint"]["state"] if r[0] == "ok" else r[1], not (r[0] == "ok" and r[1]["checkpoint"]["state"] == "ANCHORED_CURRENT"))
    finally: w.close()

    # X7: error classification boundary cases over HTTP
    def http_case(name, setup, expect_codes):
        w = World()
        try:
            setup(w)
            srv = None
            try:
                srv = make_server(w.path, 0, trusted_anchor=w.c0_file)
            except Exception as e:
                rec(f"X7-{name}", "server start", "fixed STARTUP error", f"{type(e).__name__}: {str(e)[:100]}", None); return
            th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
            try:
                try:
                    with urlopen(f"http://127.0.0.1:{srv.server_port}/api/snapshot", timeout=30) as r: status, body = r.status, r.read().decode()
                except HTTPError as e: status, body = e.code, e.read().decode()
            finally:
                srv.shutdown(); srv.server_close(); th.join()
            leak = [s for s in (str(w.dir), "Traceback", "sqlite", "SELECT", "payload") if s in body]
            rec(f"X7-{name}", "HTTP classification", f"status in {expect_codes} and no leak", f"{status} {body[:140]} leak={leak}", status in expect_codes and not leak)
        finally: w.close()
    def corrupt_policy(w):
        w.app.db.execute("DROP TRIGGER announcements_no_update"); w.app.db.execute("UPDATE recall_announcements SET policy='{not json'"); w.app.db.commit()
    http_case("corrupt-policy-json", corrupt_policy, (409, 500, 503))
    def corrupt_motor_cfg(w):
        w.app.db.execute("DROP TRIGGER motors_no_update"); w.app.db.execute("UPDATE motors SET config='[]' WHERE serial='MTR-AAA1'"); w.app.db.commit()
    http_case("corrupt-motor-config", corrupt_motor_cfg, (409, 500, 503))
    def journal_garbage(w):
        w.app.db.execute("DROP TRIGGER app_audit_no_update"); w.app.db.execute("UPDATE app_audit SET payload='{not json' WHERE seq=2"); w.app.db.commit()
    http_case("journal-payload-garbage", journal_garbage, (409, 500, 503))
    def tamper_head(w):
        w.app.db.execute("UPDATE app_audit_head SET archive_id='forged'"); w.app.db.commit()
    http_case("archive-id-substituted", tamper_head, (409,))

    # X8: concurrent independent writer process while serving; never CURRENT after first observed write
    w = World()
    try:
        srv = make_server(w.path, 0, trusted_anchor=w.c0_file)
        th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        url = f"http://127.0.0.1:{srv.server_port}/api/snapshot"
        code = "import sys;from application.service import Manufacturing;a=Manufacturing(sys.argv[1]);[a.observe('MTR-AAA2','BR-204') for _ in range(3)];a.close()"
        states = []; wrote = False; proc = None
        def get():
            try:
                with urlopen(url, timeout=30) as r: b = json.load(r); return r.status, b["checkpoint"]["state"], [v["currentReleaseEligible"] for v in b["eligibility"].values()]
            except HTTPError as e: return e.code, json.loads(e.read().decode()).get("error"), None
        for i in range(10):
            if i == 3:
                proc = subprocess.Popen([sys.executable, "-c", code, str(w.path)], cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            states.append(get())
        proc.wait(60); states.append(get())
        srv.shutdown(); srv.server_close(); th.join()
        first_non_current = next((i for i, s in enumerate(states) if s[1] != "ANCHORED_CURRENT"), None)
        back_to_current = first_non_current is not None and any(s[1] == "ANCHORED_CURRENT" for s in states[first_non_current:])
        rec("X8", "independent writer process during polling: monotonic withdrawal", "once not CURRENT, never CURRENT again; no eligible motor after write", f"states={[s[:2] for s in states]} backToCurrent={back_to_current}", not back_to_current)
    finally: w.close()

    # X10: rollback during process lifetime over HTTP (live server, DB file swapped via backup API)
    w = World()
    try:
        old = w.backup()
        srv = make_server(w.path, 0, trusted_anchor=w.c0_file); th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        url = f"http://127.0.0.1:{srv.server_port}/api/snapshot"
        def get():
            try:
                with urlopen(url, timeout=30) as r: return r.status, json.load(r)["checkpoint"]["state"]
            except HTTPError as e: return e.code, json.loads(e.read().decode()).get("error")
        a = get()
        wr = Manufacturing(w.path); wr.observe("MTR-AAA2", "BR-204"); wr.close()
        b = get()
        conn = sqlite3.connect(w.path); old.backup(conn); conn.close()
        c = get()
        srv.shutdown(); srv.server_close(); th.join()
        rec("X10", "live server: current -> extension -> rollback to exact checkpoint state", "current / prefix-only / 409 ROLLBACK (in-process)", f"{a} / {b} / {c}", a[1] == "ANCHORED_CURRENT" and b[1] == "ANCHORED_PREFIX_ONLY" and c[0] == 409)
    finally: w.close()

    # X11: REST sub-resources in PREFIX_ONLY
    w = World()
    try:
        w.app.observe("MTR-AAA2", "BR-204")
        srv = make_server(w.path, 0, trusted_anchor=w.c0_file); th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        base = f"http://127.0.0.1:{srv.server_port}"
        def get(p):
            with urlopen(base + p, timeout=60) as r: return r.status, r.read().decode()
        snap = json.loads(get("/api/snapshot")[1])
        st, body = get("/api/motors/MTR-AAA1/decisions")
        st2, body2 = get("/api/lots/BR-310/investigation")
        srv.shutdown(); srv.server_close(); th.join()
        a2_snapshot_actions = {m: [b["current"]["operationalAction"] for b in p.values()] for m, p in snap["decisions"].items()}
        rec("X11", "PREFIX_ONLY: sub-resources must not advertise release eligibility without state", "no RELEASE_ELIGIBLE without eligibility/checkpoint marker",
            f"state={snap['checkpoint']['state']}; /decisions has RELEASE_ELIGIBLE={'RELEASE_ELIGIBLE' in body} marker={'eligib' in body.lower() or 'checkpoint' in body.lower()}; /lots/.. has RELEASE_ELIGIBLE={'RELEASE_ELIGIBLE' in body2} marker={'eligib' in body2.lower() or 'checkpoint' in body2.lower()}; snapshot actions={a2_snapshot_actions}",
            not (('RELEASE_ELIGIBLE' in body2) and not ('eligib' in body2.lower() or 'checkpoint' in body2.lower())))
    finally: w.close()

    # X12: unanchored server serves sub-resources? and the legacy-status envelope
    w = World()
    try:
        srv = make_server(w.path, 0); th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
        base = f"http://127.0.0.1:{srv.server_port}"
        out = {}
        for p in ("/api/snapshot", "/api/motors", "/api/motors/MTR-AAA2/decisions", "/api/notifications"):
            try:
                with urlopen(base + p, timeout=60) as r: out[p] = r.status
            except HTTPError as e: out[p] = e.code
        with urlopen(base + "/api/snapshot", timeout=60) as r: s = json.load(r)
        srv.shutdown(); srv.server_close(); th.join()
        rec("X12", "unanchored server", "snapshot historical only (eligibility false); other APIs refused", f"{out}; state={s['checkpoint']['state']} elig={[v['currentReleaseEligible'] for v in s['eligibility'].values()]} status={s['freshness']['status']}", s["checkpoint"]["state"] == "UNANCHORED" and not any(v["currentReleaseEligible"] for v in s["eligibility"].values()))
    finally: w.close()

    # X13: startup with corrupted / substituted / missing checkpoint files
    w = World()
    try:
        cases = {}
        for name, data in [("truncated", w.c0_file.read_bytes()[:50]), ("empty", b""), ("not-json", b"\xff\xfe"), ("other-archive", None)]:
            f = w.dir / f"{name}.json"
            if data is None:
                other = World(); data = other.c0_file.read_bytes(); other.close()
            f.write_bytes(data)
            try:
                make_server(w.path, 0, trusted_anchor=f).server_close(); cases[name] = "STARTED (!)"
            except IntegrityFailure as e: cases[name] = e.code
            except Exception as e: cases[name] = type(e).__name__
        try: make_server(w.path, 0, trusted_anchor=w.dir / "missing.json").server_close(); cases["missing"] = "STARTED (!)"
        except Exception as e: cases["missing"] = type(e).__name__
        rec("X13", "corrupted / empty / non-JSON / other-archive / missing checkpoint at startup", "refuse to start; fixed codes only", json.dumps(cases), all("STARTED" not in v for v in cases.values()))
    finally: w.close()

    # X14: v2 successor chain tamper: previous file swapped at restart
    w = World()
    try:
        w.app.observe("MTR-AAA2", "BR-204"); w.snap(); s1 = export_anchor(w.app, w.c0)
        f1 = w.dir / "s1.json"; publish_candidate(f1, s1)
        r_ok = attempt(lambda: TrustedAnchor(f1, w.c0_file).verify(w.app)); r_noprev = attempt(lambda: TrustedAnchor(f1).verify(w.app))
        rec("X14", "successor activation with / without previous file", "CURRENT / PREFIX_MISMATCH", f"{r_ok[1]['state'] if r_ok[0]=='ok' else r_ok} / {r_noprev}", r_ok[0] == "ok" and r_ok[1]["state"] == "ANCHORED_CURRENT" and r_noprev == ("raise", "PREFIX_MISMATCH"))
    finally: w.close()


def main():
    t0 = time.time()
    for fn in (r_matrix, x_attacks):
        try: fn()
        except Exception:
            rec(fn.__name__, "harness", "no crash", traceback.format_exc()[-800:], "ERROR")
    OUT.write_text(json.dumps(RESULTS, indent=2))
    print(f"\n{len(RESULTS)} records in {time.time()-t0:.0f}s ->", OUT)


if __name__ == "__main__":
    main()
