import {test,expect} from '@playwright/test';
import {mkdirSync,writeFileSync,existsSync} from 'node:fs';
import {OwnedServer} from '../support/ownedServer';
import {validateSnapshot} from '../../src/domain/validate';

test('measure real startup, API, schema validation and first visible rendering',async({page,request})=>{
 const server=new OwnedServer(4210);const metrics:any={kind:'NON_SAFETY_RELIABILITY_TIMINGS',api:[],large:[]};
 try{
  let started=performance.now();await server.start();metrics.startupMs=performance.now()-started;
  for(let n=0;n<10;n++){
   started=performance.now();const response=await request.get(server.base+'/api/snapshot');
   const received=performance.now();expect(response.ok()).toBeTruthy();
   const body=await response.json();const parsed=performance.now();validateSnapshot(body);
   metrics.api.push({httpMs:received-started,jsonParseMs:parsed-received,validationMs:performance.now()-parsed});
  }
  started=performance.now();await page.goto(server.base+'/');
  await expect(page.getByRole('heading',{name:'Motor decisions'})).toBeVisible();
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  metrics.liveFirstVisibleMs=performance.now()-started;
  metrics.snapshotResources=await page.evaluate(()=>performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/snapshot')).map(r=>({start:r.startTime,duration:r.duration})));
  for(let n=0;n<3;n++){
   await page.goto('about:blank');
   started=performance.now();await page.goto(server.base+'/impact.html?mode=preview&dataset=large#/lot/bearing/BR-204/graph');
   await expect(page.getByTestId('impact-window')).toContainText('too many to draw at once');
   const ms=performance.now()-started;const drawn=await page.getByTestId('impact-node').count();
   const sample:any={firstVisibleMs:ms,drawn};metrics.large.push(sample);
   expect(drawn).toBeGreaterThan(0);expect(drawn).toBeLessThan(400);expect(ms).toBeLessThan(15000);
   started=performance.now();await page.getByRole('button',{name:'Next motors'}).click();
   await expect(page.getByTestId('impact-window')).toContainText(/page 2 of/);sample.nextPageMs=performance.now()-started;
   started=performance.now();await page.getByRole('link',{name:'List',exact:true}).click();
   await expect(page.getByRole('button',{name:/more of \d+ remaining/})).toBeVisible();sample.listMs=performance.now()-started;
  }
 }finally{
  await server.dispose();metrics.ownedDirectoryRemoved=!existsSync(server.directory);
  mkdirSync('../.tmp-reliability',{recursive:true});writeFileSync('../.tmp-reliability/latency.json',JSON.stringify(metrics,null,2)+'\n');
 }
});
