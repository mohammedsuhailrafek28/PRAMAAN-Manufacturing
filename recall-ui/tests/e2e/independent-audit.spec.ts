// Independent browser challenges. Synthetic captured backend envelopes, not a live evaluator.
import {test,expect} from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {createServer,type Server} from "node:http";
import {readFileSync,existsSync,statSync} from "node:fs";
import {resolve,join,extname} from "node:path";
const base="http://127.0.0.1:4337",dist=resolve("dist");
let mode="current",server:Server;
const types:Record<string,string>={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json"};
function envelope(){
 const e=JSON.parse(readFileSync(resolve("tests/fixtures/h1h2",(mode==="not_cleared"?"current":mode)+".json"),"utf8"));
 if(e.body.freshness?.maxAgeSeconds>0)e.body.freshness.verifiedAt=new Date().toISOString();
 if(mode==="not_cleared")e.body.eligibility["MTR-26003"].currentReleaseEligible=false;
 return e;
}
test.describe.configure({mode:"default"});
test.beforeAll(async()=>{
 server=createServer((req,res)=>{
  const path=new URL(req.url??"/",base).pathname;
  if(path==="/api/snapshot"){const e=envelope();res.writeHead(e.status,{"content-type":"application/json","cache-control":"no-store"});res.end(JSON.stringify(e.body));return;}
  if(path.startsWith("/api/")){res.writeHead(404);res.end("{}");return;}
  const f=join(dist,path==="/"?"index.html":path);
  if(!f.startsWith(dist)||!existsSync(f)||!statSync(f).isFile()){res.writeHead(404);res.end();return;}
  res.writeHead(200,{"content-type":types[extname(f)]??"application/octet-stream"});res.end(readFileSync(f));
 });await new Promise<void>(r=>server.listen(4337,"127.0.0.1",r));
});
test.afterAll(async()=>{await new Promise<void>(r=>server.close(()=>r()));});
test.beforeEach(()=>{mode="current";});
const routes=["/#/unit/MTR-26003/decision","/passport.html#/passport/MTR-26003/components","/passport.html#/passport/MTR-26003/records","/investigation.html#/evidence/MTR-26001/urn%3Apramaan%3AMTR-26001%3AASSY%3A1","/impact.html#/lot/bearing/BR-310/graph/motor%3AMTR-26003"];
for(const route of routes)test(`invalid checkpoint cannot be bypassed by ${route}`,async({page})=>{
 mode="anchor_invalid";await page.goto(base+route);await expect(page.locator("body")).toContainText(/withheld|unavailable|could not be loaded/i);
 expect(await page.locator("body").innerText()).not.toMatch(/MTR-\d|BR-\d|Release eligible|RELEASE_ELIGIBLE/);
});
test("main CURRENT keeps excluded finding with clearance withheld; other motor hold remains accessible",async({page})=>{
 mode="not_cleared";await page.goto(base+routes[0]);
 await expect(page.getByTestId("chip-finding").first()).toContainText("Excluded with evidence");
 await expect(page.getByTestId("clearance-withheld").first()).toBeVisible();
 await expect(page.getByTestId("clearance-chip")).toHaveCount(0);
 await page.goto(base+"/#/unit/MTR-26001/decision");await expect(page.getByTestId("chip-action").first()).toContainText("Recall hold");
});
test("main positive control then PREFIX facts then invalid removes all motor records",async({page})=>{
 await page.goto(base+routes[0]);await expect(page.getByTestId("clearance-chip").first()).toBeVisible();
 mode="prefix_only";await expect(page.getByTestId("console-historical")).toBeVisible({timeout:8000});
 await expect(page.getByTestId("chip-finding")).toHaveCount(0);await expect(page.getByTestId("clearance-chip")).toHaveCount(0);
 expect(await page.locator("body").innerText()).not.toMatch(/RELEASE_ELIGIBLE|Release eligible|Recall hold remains/);
 mode="anchor_invalid";await expect(page.getByTestId("load-error")).toBeVisible({timeout:8000});
 expect(await page.locator("body").innerText()).not.toMatch(/MTR-\d|BR-\d/);
});
for(const route of [routes[0],"/passport.html#/passport/MTR-26003/recall","/investigation.html#/","/impact.html#/lot/bearing/BR-310/list"])
 test(`CURRENT mobile accessibility and first-render timing ${route}`,async({page},info)=>{
 await page.setViewportSize({width:390,height:844});const started=performance.now();await page.goto(base+route);
 await expect(page.locator("body")).toContainText("MTR-26003");
 const ms=performance.now()-started;
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
 expect(overflow).toBe(false);
 const result=await new AxeBuilder({page}).analyze();expect(result.violations).toEqual([]);
 await info.attach("first-render-ms.json",{body:JSON.stringify({route,ms,kind:"synthetic envelope, local Chrome, one cold navigation; not production p95"}),contentType:"application/json"});
 await page.screenshot({path:`../docs/release-candidate-evidence/mobile-${info.testId.replace(/[^a-z0-9]/gi,"_")}.png`});
 });
