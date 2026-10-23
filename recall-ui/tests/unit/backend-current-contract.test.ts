// Additive complete-envelope proofs; original backend-source/freshness assertions remain unchanged.
import {afterEach,expect,it,vi} from "vitest";
import {readFileSync} from "node:fs";
import {join} from "node:path";
import {BackendRecallDataSource} from "../../src/data/RecallDataSource";
function current(){const b=JSON.parse(readFileSync(join(__dirname,"../fixtures/h1h2/current.json"),"utf8")).body;b.freshness.verifiedAt=new Date().toISOString();return b;}
const reply=(body:unknown)=>({ok:true,status:200,json:async()=>body});
afterEach(()=>vi.unstubAllGlobals());
it("complete CURRENT command passes token and preserves the validated snapshot",async()=>{
 const snap=current();const fetcher=vi.fn().mockResolvedValueOnce(reply({token:"synthetic-test-token"})).mockResolvedValueOnce(reply({snapshot:snap,captureToDecisionMs:9}));vi.stubGlobal("fetch",fetcher);
 const result=await new BackendRecallDataSource().command("units",{serial:"MTR-AUDIT-001"});
 expect(result.snapshot).toBe(snap);expect(result.captureToDecisionMs).toBe(9);
 expect(fetcher.mock.calls[1][0]).toBe("/api/units");expect(fetcher.mock.calls[1][1].headers["X-Pramaan-Token"]).toBe("synthetic-test-token");
});
it("late older complete CURRENT response cannot replace the accepted newer request",async()=>{
 let first!:(v:unknown)=>void,second!:(v:unknown)=>void;
 vi.stubGlobal("fetch",vi.fn().mockImplementationOnce(()=>new Promise(r=>{first=r;})).mockImplementationOnce(()=>new Promise(r=>{second=r;})));
 const source=new BackendRecallDataSource();const old=source.load();const rejection=expect(old).rejects.toThrow("Superseded");const newer=source.load();
 const snap=current();second(reply(snap));await expect(newer).resolves.toBe(snap);first(reply(current()));await rejection;
});
it("a complete but expired CURRENT response fails with the typed lease category",async()=>{
 const snap=current();snap.freshness.verifiedAt=new Date(Date.now()-6000).toISOString();vi.stubGlobal("fetch",vi.fn().mockResolvedValue(reply(snap)));
 await expect(new BackendRecallDataSource().load()).rejects.toMatchObject({gate:{kind:"WITHHELD",cause:"LEASE_EXPIRED"}});
});
it("body read timeout fails closed rather than displaying the prior complete snapshot",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,status:200,json:()=>new Promise(()=>{})}));
 await expect(new BackendRecallDataSource(25).load()).rejects.toThrow("timed out");
});
