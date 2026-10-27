"""Reproducible synthetic impact workload. Truth is fixture intent, outside all product code.

Uses existing public Manufacturing commands to create eight prototypes, then production
Ledger.register_motor/capture for every target motor (one explicitly authorized synthetic
aggregator per motor). No direct event/capture/hash insertion or disabled validation.
This is compact-source synthetic scaling, not a real factory-source distribution.
"""
import argparse
from collections import Counter
import cProfile
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import pstats
import sqlite3
import statistics
import tempfile
import time

from application.service import Manufacturing, encode_document
from performance.impact_query import ImpactQuery

BASE="6709b0c6f521006cf6332caeecec6b08dbd44e84"

def category(i):
    k=i%100
    return "de" if k<5 else "nde" if k<10 else "removed" if k<15 else "sighting" if k<20 else "gap" if k<25 else "empty" if k==25 else "double" if k==26 else "clean"

def prototypes(directory):
    app=Manufacturing(directory/"prototypes.sqlite")
    result={}
    try:
        for kind in ("clean","de","nde","removed","sighting","gap","empty","double"):
            motor="MTR-TEMPLATE-"+kind.upper()
            app.create_unit(motor,gap=kind=="gap")
            if kind!="empty":
                app.assemble(motor,"BR-204" if kind in ("de","removed","gap") else "BR-310", "BR-204" if kind=="nde" else "BR-312")
                app.record_historical_shipment_fixture(motor)
            if kind in ("removed","gap"): app.replace(motor,"BR-312")
            if kind=="sighting": app.observe(motor,"BR-2O4")
            if kind=="double":
                old=next(e for e in app.events(motor) if e["eventType"]=="COMPONENT_INSTALLED" and e["payload"]["slot"]=="DE")
                p=dict(old["payload"])
                app.event(motor,"COMPONENT_INSTALLED","REWORK",p,work_order="BUILD-"+motor)
            result[kind]=(motor,app.ledger._config(motor),app.events(motor))
    finally:
        app.close()
    return result

def build(path,n):
    templates=prototypes(path.parent)
    app=Manufacturing(path)
    truth={};start=time.perf_counter()
    try:
        for i in range(n):
            kind=category(i);old,config,events=templates[kind];motor=f"MTR-PERF-{i:05d}"
            rename=lambda x:json.loads(json.dumps(x).replace(old,motor).replace("SHP-26-"+old.removeprefix("MTR-"),"SHP-26-"+motor.removeprefix("MTR-")))
            config=rename(config);events=rename(events);source="BENCH:"+motor
            actors=sorted({e["actorId"] for e in events}) or ["SYNTHETIC-AGGREGATOR"]
            sources={source:dict(streamScope="MOTOR",actors=actors,eventTypes=sorted({e["eventType"] for e in events}) or ["COMPONENT_INSTALLED"])}
            sessions=[dict(s,sourceId=source,sessionId="session:"+source if not s["sessionId"].startswith("old:") else "old:"+motor)
                      for s in config["sessions"] if s["sourceId"].startswith("ASSY:")]
            for rule in config["coverage"]["mandatoryCapture"]: rule["sources"]=[source]
            config["coverage"]["trustedVerifierSources"]=[]
            config["coverage"]["slotAttribution"]["accessEvidenceSources"]=[]
            app.ledger.register_motor(motor,sources=sources,sessions=sessions,coverage=config["coverage"])
            with app.db: app.db.execute("INSERT INTO app_units VALUES(?,?)",(motor,kind))
            for j,e in enumerate(events,1):e.update(sourceId=source,sourceSeq=j,captureSessionId="session:"+source)
            if events:
                raw=json.dumps(encode_document(events,"2026-12-31T23:59:59Z"),separators=(",",":")).encode()
                app.ledger.capture(motor,raw,producer_source=source,expected_sha256=hashlib.sha256(raw).hexdigest())
            truth[motor]=dict(scenario=kind,expectedCandidate=kind!="clean",shipment=kind!="empty")
            if (i+1)%1000==0:print(f"captured {i+1}/{n}: {time.perf_counter()-start:.1f}s",flush=True)
        counts={t:app.db.execute("SELECT count(*) FROM "+t).fetchone()[0] for t in ("events","captures","motors")}
    finally:
        app.close()
    return truth,dict(seconds=time.perf_counter()-start,counts=counts)

def stats(samples):
    s=sorted(samples)
    def q(p):
        k=(len(s)-1)*p;lo=math.floor(k);hi=math.ceil(k);return s[lo]+(s[hi]-s[lo])*(k-lo)
    return dict(n=len(s),p50Ms=q(.5),p95Ms=q(.95),minMs=s[0],maxMs=s[-1])

def measure(n,reps,out,profile=False):
    with tempfile.TemporaryDirectory(prefix="pramaan-perf-") as tmp:
        path=Path(tmp)/"ledger.sqlite";truth,seed=build(path,n)
        reader=ImpactQuery(path)
        try:
            start=time.perf_counter();meta=reader.rebuild();cold=(time.perf_counter()-start)*1000
            samples=[];serialized=[];result=None
            for _ in range(reps):
                start=time.perf_counter();result=reader.query("BR-204");duration=(time.perf_counter()-start)*1000
                encoded=json.dumps(result,separators=(",",":")).encode();samples.append(duration);serialized.append((time.perf_counter()-start)*1000)
            start=time.perf_counter();prepared=reader.query_json("BR-204");first_json=(time.perf_counter()-start)*1000
            json_samples=[]
            for _ in range(reps):
                start=time.perf_counter();payload=reader.query_json("BR-204");json_samples.append((time.perf_counter()-start)*1000)
                assert payload==prepared
            assert json.loads(prepared)==result
            actual={m["motorSerial"] for m in result["motors"]};expected={m for m,t in truth.items() if t["expectedCandidate"]}
            actualships={(m["motorSerial"],s["shipmentId"]) for m in result["motors"] for s in m["shipments"]}
            expectedships={(m,"SHP-26-"+m.removeprefix("MTR-")) for m in expected if truth[m]["shipment"]}
            res=dict(base=BASE,motors=n,seed=seed,verified=meta,coldVerifiedIndexBuildMs=cold,
                     warmQuery=stats(samples),warmQueryPlusJson=stats(serialized),firstReadyJsonMs=first_json,readyJsonWarm=stats(json_samples),responseBytes=len(encoded),
                     correctness=dict(expectedCandidates=len(expected),actualCandidates=len(actual),missed=sorted(expected-actual),extra=sorted(actual-expected),
                                      missedShipmentLinks=sorted(expectedships-actualships),extraShipmentLinks=sorted(actualships-expectedships)),
                     scenarios=dict(Counter(t["scenario"] for t in truth.values())),hardware=dict(python=platform.python_version(),platform=platform.platform(),sqlite=sqlite3.sqlite_version,processor=platform.processor()),
                     semantics="Recorded potential impact only, no current decisions/clearance; dense historic/uncertain candidates included")
            if n==100:
                app=Manufacturing(path);timings=[]
                for _ in range(3):
                    start=time.perf_counter()
                    for motor in truth:
                        wm=app.ledger.watermark(motor);app.ledger.snapshot(motor,wm)
                    timings.append((time.perf_counter()-start)*1000)
                res["baselineVerifiedFleetGenealogy"]=stats(timings)
                app.announce("BR-204",["DE"])
                pr=cProfile.Profile();start=time.perf_counter();pr.enable();app.snapshot();pr.disable()
                res["baselineFullSnapshotFirstMs"]=(time.perf_counter()-start)*1000
                start=time.perf_counter();app.snapshot();res["baselineFullSnapshotRepeatMs"]=(time.perf_counter()-start)*1000
                stream=io.StringIO();pstats.Stats(pr,stream=stream).sort_stats("cumulative").print_stats(30)
                (out/"profile-100.txt").write_text(stream.getvalue(),encoding="utf8")
                app.close()
        finally:
            reader.close()
        (out/f"n{n}.json").write_text(json.dumps(res,indent=2),encoding="utf8")
        print(json.dumps({"n":n,"warm":res["warmQuery"],"json":res["warmQueryPlusJson"],"coldMs":cold,"correctness":res["correctness"]}),flush=True)
        return res

def main():
    p=argparse.ArgumentParser();p.add_argument("--sizes",type=int,nargs="+",default=[100,1000,10000]);p.add_argument("--reps",type=int,default=15);p.add_argument("--out",type=Path,default=Path("docs/ps10-performance/benchmarks"));a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    for n in a.sizes:measure(n,a.reps,a.out)
if __name__=="__main__":main()
