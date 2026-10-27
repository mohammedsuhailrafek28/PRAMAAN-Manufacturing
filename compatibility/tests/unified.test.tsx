import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const nav=vi.hoisted(()=>({path:'/dashboard/report',query:'',push:vi.fn(),replace:vi.fn()}));
vi.mock('next/navigation',()=>({usePathname:()=>nav.path,useSearchParams:()=>new URLSearchParams(nav.query),useRouter:()=>({push:nav.push,replace:nav.replace})}));
vi.mock('next/link',()=>({default:({children,href,...rest}:React.PropsWithChildren<{href:string}>)=><a href={href} {...rest}>{children}</a>}));

import { DataProvider, useData, useMotorResource } from '../../stitch-nextjs/src/dash/data';
import ResolutionTrail from '../../stitch-nextjs/src/dash/Trail';
import ReportPage from '../../stitch-nextjs/src/app/(dashboard)/dashboard/report/page';

const load=(name:string)=>JSON.parse(readFileSync(resolve(process.env.PRAMAAN_COMPAT_FIXTURES!,name+'.json'),'utf8'));
let data:ReturnType<typeof load>, httpStatus=200, error='VERIFYING';
let received:Array<{path:string;method:string}>, blobs:Blob[], downloads:string[];
let fetchMock:ReturnType<typeof vi.fn>;
const current=()=>load('manufacturing-current');

beforeEach(()=>{
  data=current();httpStatus=200;error='VERIFYING';received=[];blobs=[];downloads=[];nav.query='';nav.path='/dashboard/report';
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(Date.parse(data.freshness.verifiedAt));
  Object.defineProperty(document,'hidden',{configurable:true,value:false});
  fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input);received.push({path,method:init?.method??'GET'});
    if(httpStatus!==200)return new Response(JSON.stringify({error,state:httpStatus===409?'ANCHOR_INVALID':undefined}),{status:httpStatus});
    if(path==='/api/snapshot')return new Response(JSON.stringify(data),{status:200});
    const match=path.match(/^\/api\/motors\/([^/]+)\/decisions$/);
    if(match)return new Response(JSON.stringify({...data.decisions[decodeURIComponent(match[1])],checkpoint:data.checkpoint,eligibility:data.eligibility?.[decodeURIComponent(match[1])]}),{status:200});
    throw Error('Unexpected test request '+path);
  });
  vi.stubGlobal('fetch',fetchMock);
  Object.defineProperty(URL,'createObjectURL',{configurable:true,value:vi.fn((b:Blob)=>{blobs.push(b);return 'blob:owned-test';})});
  Object.defineProperty(URL,'revokeObjectURL',{configurable:true,value:vi.fn()});
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){downloads.push(this.download);});
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});

function TrailHost({motor}:{motor:string}){
  const {snap}=useData();
  return snap.phase==='ready'?<ResolutionTrail s={snap.snap} motor={motor} setMotor={()=>undefined}/>:null;
}
const report=()=>render(<DataProvider><ReportPage/></DataProvider>);
const trail=(motor:string)=>render(<DataProvider><TrailHost motor={motor}/></DataProvider>);

describe('stable frontend against actual manufacturing snapshots — no frontend service',()=>{
  it('renders nine-motor report with actual QC PASS and held-risk counts',async()=>{
    report();await screen.findByTestId('rp-risks');
    expect(screen.getByTestId('rp-prov')).toHaveTextContent('9 motors; 47 ledger events');
    expect(screen.getByTestId('rp-qc')).toHaveTextContent(/1.*pass/i);
    expect(screen.getByTestId('rp-risks')).toHaveTextContent('MTR-27002');
    expect(screen.getByTestId('rp-currentstate')).toHaveTextContent('Current state at report generation');
  });

  it('keeps the original five-motor report independently reproducible',async()=>{
    data=load('five-current');vi.setSystemTime(Date.parse(data.freshness.verifiedAt));report();
    await screen.findByTestId('rp-risks');expect(screen.getByTestId('rp-prov')).toHaveTextContent('5 motors; 58 ledger events');
    expect(screen.getByTestId('rp-risks')).toHaveTextContent('MTR-26005');
  });

  it('exports PDF only after an additional fresh authoritative GET',async()=>{
    report();await screen.findByTestId('rp-risks');const n=received.length;
    fireEvent.click(screen.getByTestId('rp-export'));
    await waitFor(()=>expect(downloads).toHaveLength(1));
    expect(received.slice(n).some(r=>r.path==='/api/snapshot')).toBe(true);
    expect(blobs[0].type).toBe('application/pdf');expect(blobs[0].size).toBeGreaterThan(1000);
    expect(downloads[0]).toMatch(/^PRAMAAN_Daily_Report_.*\.pdf$/);
    expect(received.every(r=>r.method==='GET')).toBe(true);
  });

  it('does not export cached current decisions when fresh verification returns 503 VERIFYING',async()=>{
    report();await screen.findByTestId('rp-risks');httpStatus=503;
    fireEvent.click(screen.getByTestId('rp-export'));
    await waitFor(()=>expect(screen.getByTestId('rp-export-status')).toHaveTextContent('Export unavailable'));
    expect(downloads).toHaveLength(0);expect(blobs).toHaveLength(0);
  });

  it('withdraws export when the original five-second freshness lease has expired',async()=>{
    report();await screen.findByTestId('rp-risks');vi.setSystemTime(Date.now()+6000);
    fireEvent.click(screen.getByTestId('rp-export'));
    await waitFor(()=>expect(screen.getByTestId('rp-export-status')).toHaveTextContent('Export unavailable'));
    expect(downloads).toHaveLength(0);
  });

  it.each(['manufacturing-stale','manufacturing-unanchored'])('exports %s only as facts with current risks withheld',async name=>{
    data=load(name);report();await screen.findByTestId('rp-notcurrent');
    expect(screen.queryByTestId('rp-risks')).toBeNull();
    fireEvent.click(screen.getByTestId('rp-export'));
    await waitFor(()=>expect(downloads).toHaveLength(1));
    expect(screen.getByTestId('rp-export-status')).toHaveTextContent('NOT CURRENT');
  });

  it.each([[409,'ANCHOR_INVALID'],[503,'VERIFYING']])('unavailable response %s produces no report, fallback data or export control',async(status,code)=>{
    httpStatus=status as number;error=code as string;report();
    await screen.findByText('The report is unavailable.');
    expect(screen.queryByTestId('daily-report')).toBeNull();expect(screen.queryByTestId('rp-export')).toBeNull();
  });

  it('new evidence on the same archive withdraws cached report risks until checkpoint renewal',async()=>{
    report();await screen.findByTestId('rp-risks');
    const before=data.freshness.archiveId;data=load('manufacturing-stale');
    expect(data.freshness.archiveId).toBe(before);vi.setSystemTime(Date.parse(data.freshness.verifiedAt));
    fireEvent.click(screen.getByTestId('rp-generate'));
    await screen.findByTestId('rp-notcurrent');expect(screen.queryByTestId('rp-risks')).toBeNull();
    expect(screen.getByTestId('rp-notcurrent')).toHaveTextContent('Anchored prefix only');
  });

  it('Resolution Trail shows actual rework and unresolved outcome for the original ambiguous replacement',async()=>{
    data=load('five-current');vi.setSystemTime(Date.parse(data.freshness.verifiedAt));trail('MTR-26002');
    await screen.findByTestId('trail-outcome');
    expect(screen.getByTestId('trail-step-02')).toHaveTextContent('BR-312');
    expect(screen.getByTestId('trail-outcome')).toHaveTextContent('AMBIGUOUS_SLOT_ATTRIBUTION');
    expect(screen.getByTestId('trail-outcome')).toHaveTextContent('RECALL HOLD');
    expect(screen.getByTestId('trail-confirmation')).toHaveTextContent('NO INDEPENDENT CONFIRMATION RECORDED');
  });

  it('native manufacturing QC PASS stays a claim while the actual affected motor remains held',async()=>{
    trail('MTR-27002');await screen.findByTestId('trail-outcome');
    expect(screen.getByTestId('trail-step-03')).toHaveTextContent('PASS');
    expect(screen.getByTestId('trail-confirmation')).toHaveTextContent('NO INDEPENDENT CONFIRMATION RECORDED');
    expect(screen.getByTestId('trail-outcome')).toHaveTextContent('RECALL HOLD');
    expect(screen.getByTestId('trail-no-corrective')).toHaveTextContent('No corrective action recorded');
  });

  it('prefix-only Resolution Trail withholds decision sections and never requests current decisions',async()=>{
    data=load('manufacturing-stale');trail('MTR-27002');
    await screen.findAllByTestId('trail-withheld');expect(screen.queryByTestId('trail-outcome')).toBeNull();
    expect(received.some(r=>r.path.endsWith('/decisions'))).toBe(false);
    expect(within(screen.getByTestId('trail-step-03')).getByText(/Inspection recorded: PASS/)).toBeVisible();
  });
});

// Regression for the previously characterized risk: a successful new gated snapshot must invalidate a same-motor subresource.
// (Exhaustive epoch, late-response, archive, withdrawal and prefix-only cases are in consistency.test.tsx.)
function ConsistencyProbe(){
  const {snap,gate}=useData();
  const res=useMotorResource<Record<string,any>>('decisions',gate.decisionsAllowed?'MTR-27002':null);
  const s=snap.phase==='ready'?snap.snap:null;
  const bundle=res?.ok?Object.entries(res.body).find(([k])=>k!=='checkpoint'&&k!=='eligibility')?.[1]:null;
  const cur=s?Object.values(s.decisions['MTR-27002']??{})[0]?.current:null;
  return <div><span data-testid="snapshot-decision">{String(cur?.decisionId??'none')}</span><span data-testid="resource-decision">{String(bundle?.current?.decisionId??'none')}</span></div>;
}
it('refetches same-motor history after an independently gated successor snapshot instead of keeping the previous decision',async()=>{
  const old=Object.values(data.decisions['MTR-27002'])[0] as any;
  const next=load('manufacturing-successor');
  const newer=Object.values(next.decisions['MTR-27002'])[0] as any;
  expect(newer.current.decisionId).not.toBe(old.current.decisionId);
  render(<DataProvider><ConsistencyProbe/></DataProvider>);
  await waitFor(()=>expect(screen.getByTestId('resource-decision')).toHaveTextContent(old.current.decisionId));
  data=next;vi.setSystemTime(Date.parse(next.freshness.verifiedAt));
  await waitFor(()=>expect(screen.getByTestId('snapshot-decision')).toHaveTextContent(newer.current.decisionId),{timeout:4000});
  await waitFor(()=>expect(screen.getByTestId('resource-decision')).toHaveTextContent(newer.current.decisionId),{timeout:4000});
  expect(received.filter(r=>r.path==='/api/motors/MTR-27002/decisions')).toHaveLength(2);
});
