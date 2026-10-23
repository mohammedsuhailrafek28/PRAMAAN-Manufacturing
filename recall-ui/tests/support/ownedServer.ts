/** Test-only ownership. Never attach to or kill an existing listener. */
import {spawn,type ChildProcess} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,dirname} from 'node:path';
import {createServer} from 'node:net';

async function free(port:number) {
 await new Promise<void>((ok,fail)=>{
  const s=createServer();s.once('error',()=>fail(new Error(`Test port ${port} already occupied; no process reused`)));
  s.listen(port,'127.0.0.1',()=>s.close(e=>e?fail(e):ok()));
 });
}
export class OwnedServer {
 readonly directory=mkdtempSync(join(tmpdir(),'pramaan-reliability-owned-'));
 readonly database=join(this.directory,'db.sqlite');
 readonly base:string;
 private child:ChildProcess|undefined;
 private diagnostics='';
 constructor(readonly port:number,private unanchored=false){this.base=`http://127.0.0.1:${port}`;}
 async start() {
  await this.stop();await free(this.port);
  const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
  const args=this.unanchored ? ['-c','import sys;from application.service import Manufacturing;from application.server import make_server;a=Manufacturing(sys.argv[1]);a.seed_demo();a.close();s=make_server(sys.argv[1],int(sys.argv[2]));s.serve_forever()',this.database,String(this.port)] : ['recall-ui/tests/browser_server.py',this.database,'--port',String(this.port)];
  const child=this.child=spawn(python,args,{cwd:resolve('..'),windowsHide:true,stdio:['ignore','pipe','pipe']});
  child.stdout?.on('data',d=>{this.diagnostics=(this.diagnostics+String(d)).slice(-8000);});
  child.stderr?.on('data',d=>{this.diagnostics=(this.diagnostics+String(d)).slice(-8000);});
  let spawnError:Error|undefined;child.once('error',e=>{spawnError=e;});
  for(let n=0;n<80;n++) {
   if(spawnError || child.exitCode!==null || child.signalCode!==null)throw new Error(`Owned test server exited: ${spawnError?.message ?? child.exitCode}; ${this.diagnostics}`);
   try{if((await fetch(this.base+'/api/session',{signal:AbortSignal.timeout(750)})).ok)return;}catch{/* not ready */}
   await new Promise(r=>setTimeout(r,250));
  }
  throw new Error(`Owned test server readiness timed out on ${this.port}; ${this.diagnostics}`);
 }
 async stop() {
  const child=this.child;
  if(!child)return;
  if(child.exitCode===null && child.signalCode===null)await new Promise<void>((ok,fail)=>{
   const timer=setTimeout(()=>fail(new Error(`Owned test server did not exit on ${this.port}`)),5000);
   child.once('close',()=>{clearTimeout(timer);ok();});
   child.once('error',e=>{clearTimeout(timer);fail(e);});
   child.kill();
  });
  this.child=undefined;
 }
 async dispose() {
  await this.stop();
  const root=resolve(this.directory);
  if(dirname(root)!==resolve(tmpdir()) || !root.split(/[\\/]/).pop()!.startsWith('pramaan-reliability-owned-'))throw new Error('Refusing cleanup outside owned temp directory');
  rmSync(root,{recursive:true,force:false,maxRetries:10,retryDelay:100});
 }
}
