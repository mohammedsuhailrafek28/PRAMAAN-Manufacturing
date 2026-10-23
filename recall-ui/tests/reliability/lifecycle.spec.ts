import {test,expect} from '@playwright/test';
import {createServer} from 'node:net';
import {existsSync} from 'node:fs';
import {OwnedServer} from '../support/ownedServer';

test('occupied port refuses reuse and cleans only its owned directory',async()=>{
 const foreign=createServer(socket=>socket.end());
 await new Promise<void>(ok=>foreign.listen(4211,'127.0.0.1',ok));
 const owned=new OwnedServer(4211);
 try{
  await expect(owned.start()).rejects.toThrow(/already occupied/);
  await owned.dispose();expect(existsSync(owned.directory)).toBe(false);
  expect(foreign.listening).toBe(true);
 }finally{await new Promise<void>(ok=>foreign.close(()=>ok()));}
});

test('throwing test body still removes database, anchor and listener',async()=>{
 const owned=new OwnedServer(4212);
 let error:unknown;
 try{await owned.start();expect(existsSync(owned.database)).toBe(true);throw new Error('intentional test-body failure');}
 catch(e){error=e;}
 finally{await owned.dispose();}
 expect((error as Error).message).toBe('intentional test-body failure');
 expect(existsSync(owned.directory)).toBe(false);
 await expect(fetch(owned.base+'/api/session',{signal:AbortSignal.timeout(500)})).rejects.toThrow();
});
