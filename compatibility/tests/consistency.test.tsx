import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

const nav=vi.hoisted(()=>({path:'/dashboard/recall',query:'',push:vi.fn(),replace:vi.fn()}));
vi.mock('next/navigation',()=>({usePathname:()=>nav.path,useSearchParams:()=>new URLSearchParams(nav.query),useRouter:()=>({push:nav.push,replace:nav.replace})}));
vi.mock('next/link',()=>({default:({children,href,...rest}:React.PropsWithChildren<{href:string}>)=><a href={href} {...rest}>{children}</a>}));

import { DataProvider, useData, useMotorResourceChecked } from '../../stitch-nextjs/src/dash/data';
import ResolutionTrail from '../../stitch-nextjs/src/dash/Trail';

// Real snapshots and per-motor bodies from owned ephemeral manufacturing databases (compatibility/run.py). The fetch layer is the only fake.
const load=(name:string)=>JSON.parse(readFileSync(resolve(process.env.PRAMAAN_COMPAT_FIXTURES!,name+'.json'),'utf8'));
const M='MTR-27002';
const DEC=`/api/motors/${M}/decisions`, LIFE=`/api/motors/${M}/lifecycle`, PROV=`/api/motors/${M}/provenance`;
type Res={decisions:Record<string,any>;lifecycle:Record<string,any>;provenance:Record<string,any>};
let snapshot:any, res:Res, httpStatus:number, received:string[];
let holds:Map<string,Array<Promise<void>>>;
const cur=()=>({snap:load('manufacturing-current'),res:load('resources-manufacturing-current') as Res});
const nxt=()=>({snap:load('manufacturing-successor'),res:load('resources-manufacturing-successor') as Res});
const stl=()=>({snap:load('manufacturing-stale'),res:load('resources-manufacturing-stale') as Res});
const use=(x:{snap:any;res:Res})=>{snapshot=x.snap;res=x.res;vi.setSystemTime(Date.parse(x.snap.freshness.verifiedAt));};
const hold=(path:string)=>{let release!:()=>void;const p=new Promise<void>(r=>{release=r;});holds.set(path,[...(holds.get(path)??[]),p]);return release;};
const count=(path:string)=>received.filter(p=>p===path).length;

beforeEach(()=>{
  received=[];holds=new Map();httpStatus=200;use(cur());
  vi.useFakeTimers({toFake:['Date']});use(cur());
  Object.defineProperty(document,'hidden',{configurable:true,value:false});
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>{
    const path=String(input);received.push(path);
    if(httpStatus!==200)return new Response(JSON.stringify({error:'VERIFYING'}),{status:httpStatus});
    // The body is fixed when the request is served; a held response is delivered later, from that earlier state.
    let body:unknown;
    if(path==='/api/snapshot')body=snapshot;
    else{const m=path.match(/^\/api\/motors\/([^/]+)\/(decisions|lifecycle|provenance)$/);if(!m)throw Error('Unexpected test request '+path);
      body=(res as any)[m[2]][decodeURIComponent(m[1])];if(body===undefined)return new Response(JSON.stringify({error:'CHECKPOINT_REQUIRED'}),{status:409});}
    const text=JSON.stringify(body);const gate=holds.get(path)?.shift();if(gate)await gate;
    return new Response(text,{status:200});
  }));
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});

const idOf=(r:any)=>{const b=r?.res?.ok?r.res.body:null;const k=b&&Object.keys(b).find(x=>x!=='checkpoint'&&x!=='eligibility');return k?b[k].current.decisionId as string:'none';};
let log:string[];
function Probe({decisions=true}:{decisions?:boolean}){
  const {snap,gate}=useData();
  const d=useMotorResourceChecked<any>('decisions',decisions&&gate.decisionsAllowed?M:null);
  const l=useMotorResourceChecked<any>('lifecycle',M);
  const p=useMotorResourceChecked<any>('provenance',M);
  const s=snap.phase==='ready'?snap.snap:null;
  const snapId=s?String(Object.values<any>(s.decisions[M]??{})[0]?.current?.decisionId??'none'):'no-snapshot';
  const dec=idOf(d);
  React.useEffect(()=>{log.push(`${d.consistency}|snap=${snapId}|res=${dec}`);});
  return <div><span data-testid="snap-id">{snapId}</span><span data-testid="dec-state">{d.consistency}</span><span data-testid="dec-id">{dec}</span>
    <span data-testid="life-state">{l.consistency}</span><span data-testid="life-reason">{l.reason}</span><span data-testid="life-count">{l.res?.ok?String(l.res.body.eventCount):'none'}</span>
    <span data-testid="prov-state">{p.consistency}</span></div>;
}
const t=(id:string)=>screen.getByTestId(id).textContent;
const mount=(decisions=true)=>{log=[];return render(<DataProvider><Probe decisions={decisions}/></DataProvider>);};
const ids=()=>({old:idOf({res:{ok:true,body:cur().res.decisions[M]}}),new:idOf({res:{ok:true,body:nxt().res.decisions[M]}})});
const neverStale=()=>expect(log.filter(l=>{const[state,snap,r]=l.split('|');return state==='CURRENT'&&snap.slice(5)!==r.slice(4);})).toEqual([]);
const T=15000;

describe('per-motor resources stay bound to the verified snapshot',()=>{
  it('fixtures differ between checkpoints',()=>{expect(ids().old).not.toBe(ids().new);});

  it('snapshot advancement after a fetch drops the cached resource and refetches under the new epoch',async()=>{
    mount();await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));
    expect(t('dec-id')).toBe(ids().old);expect(t('life-state')).toBe('CURRENT');expect(t('prov-state')).toBe('UNVERIFIED');
    use(nxt());
    await waitFor(()=>expect(t('dec-id')).toBe(ids().new),{timeout:6000});await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));
    expect(count(DEC)).toBe(2);expect(count(LIFE)).toBe(2);neverStale();
  },T);

  it('a resource that lags the snapshot is withheld, then recovers on the next verified snapshot',async()=>{
    mount();await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));
    const n=nxt();snapshot=n.snap;vi.setSystemTime(Date.parse(n.snap.freshness.verifiedAt)); // backend serves the new snapshot but still the old per-motor bodies
    await waitFor(()=>expect(t('dec-state')).toBe('MISMATCH'),{timeout:6000});
    expect(t('dec-id')).toBe('none');expect(t('life-state')).toBe('MISMATCH');expect(t('life-count')).toBe('none');
    // Same epoch, same bodies: the mismatch is not retried into a CURRENT label. A withdrawal and a re-verified snapshot clear it.
    await new Promise(r=>setTimeout(r,2500));expect(t('dec-state')).toBe('MISMATCH');expect(count(DEC)).toBe(2);
    httpStatus=503;await waitFor(()=>expect(t('dec-state')).toBe('PENDING'),{timeout:6000});
    res=n.res;httpStatus=200; // the backend now serves matching bodies for the re-verified snapshot
    await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'),{timeout:6000});expect(t('dec-id')).toBe(ids().new);expect(t('life-state')).toBe('CURRENT');neverStale();
  },T);

  it('a late response from the previous request epoch is discarded',async()=>{
    const release=hold(DEC);mount();
    await waitFor(()=>expect(count(DEC)).toBe(1)); // request for the old epoch is in flight, carrying the old decision
    expect(t('dec-state')).toBe('PENDING');
    use(nxt());
    await waitFor(()=>expect(t('dec-id')).toBe(ids().new),{timeout:6000});await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));
    release();await new Promise(r=>setTimeout(r,50));
    expect(t('dec-id')).toBe(ids().new);expect(t('dec-state')).toBe('CURRENT');expect(log.some(l=>l.endsWith('res='+ids().old)&&l.startsWith('CURRENT|snap='+ids().new))).toBe(false);neverStale();
  },T);

  it('switching archive is rejected by the original gate and withdraws every cached resource',async()=>{
    mount();await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));expect(t('life-state')).toBe('CURRENT');
    const other=structuredClone(snapshot);other.freshness.archiveId='archive-switched-for-test';snapshot=other;
    await waitFor(()=>expect(t('dec-state')).toBe('PENDING'),{timeout:6000});
    expect(t('dec-id')).toBe('none');expect(t('life-state')).toBe('PENDING');expect(t('life-count')).toBe('none');expect(t('prov-state')).toBe('PENDING');
    expect(count(DEC)).toBe(1);expect(count(LIFE)).toBe(1); // nothing is requested or reused under the other archive
  },T);

  it('checkpoint withdrawal removes every resource and a new verified snapshot restores them by refetching',async()=>{
    mount();await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));expect(t('life-state')).toBe('CURRENT');
    httpStatus=503;
    await waitFor(()=>expect(t('dec-state')).toBe('PENDING'),{timeout:6000});
    expect(t('dec-id')).toBe('none');expect(t('life-state')).toBe('PENDING');expect(t('life-count')).toBe('none');expect(t('prov-state')).toBe('PENDING');
    httpStatus=200; // the same verified snapshot returns: nothing cached before the withdrawal may be reused
    await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'),{timeout:6000});
    expect(count(DEC)).toBe(2);expect(count(LIFE)).toBe(2);expect(count(PROV)).toBe(2);
  },T);

  it('moving to prefix-only withdraws decisions and keeps history only as UNVERIFIED recorded fact',async()=>{
    mount();await waitFor(()=>expect(t('dec-state')).toBe('CURRENT'));
    use(stl());
    await waitFor(()=>expect(t('dec-state')).toBe('PENDING'),{timeout:6000});
    expect(t('dec-id')).toBe('none');
    await waitFor(()=>expect(t('life-state')).toBe('UNVERIFIED'),{timeout:6000});expect(t('life-reason')).toMatch(/not current/);
    expect(count(DEC)).toBe(1); // no decision is ever requested for a prefix-only snapshot
  },T);

  it('prefix-only from the start: never CURRENT, no decision request',async()=>{
    use(stl());mount();
    await waitFor(()=>expect(t('life-state')).toBe('UNVERIFIED'),{timeout:6000});await waitFor(()=>expect(t('prov-state')).toBe('UNVERIFIED'));
    expect(t('dec-state')).toBe('PENDING');expect(count(DEC)).toBe(0);expect(screen.getByTestId('dec-id').textContent).toBe('none');
  },T);

  it('unavailable verification: nothing is requested or shown beyond the snapshot attempt',async()=>{
    httpStatus=503;mount();await new Promise(r=>setTimeout(r,300));
    expect(received.every(p=>p==='/api/snapshot')).toBe(true);
    expect(['dec-state','life-state','prov-state'].map(t)).toEqual(['PENDING','PENDING','PENDING']);expect(t('snap-id')).toBe('no-snapshot');
  },T);

  it('Resolution Trail withholds a decision history that lags the snapshot and says why',async()=>{
    function Host(){const {snap}=useData();return snap.phase==='ready'?<ResolutionTrail s={snap.snap} motor={M} setMotor={()=>undefined}/>:null;}
    render(<DataProvider><Host/></DataProvider>);await screen.findByTestId('trail-outcome');
    const n=nxt();snapshot=n.snap;vi.setSystemTime(Date.parse(n.snap.freshness.verifiedAt));
    await screen.findByTestId('trail-mismatch',undefined,{timeout:6000});
    expect(screen.queryByTestId('trail-outcome')).toBeNull();expect(screen.getByTestId('trail-mismatch')).toHaveTextContent('does not match the verified snapshot');
    httpStatus=503;await waitFor(()=>expect(screen.queryByTestId('trail-mismatch')).toBeNull(),{timeout:6000});
    res=n.res;httpStatus=200;
    await screen.findByTestId('trail-outcome',undefined,{timeout:6000});expect(screen.queryByTestId('trail-mismatch')).toBeNull();
  },T);
});
