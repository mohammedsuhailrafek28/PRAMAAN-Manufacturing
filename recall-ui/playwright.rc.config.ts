// Isolated replay of every unchanged browser assertion while another audit owns 4173.
// One worker also serializes the two original tests that both own auxiliary port 4185.
import {defineConfig} from "@playwright/test";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve} from "node:path";
export default defineConfig({
 testDir:"tests/e2e",timeout:30000,fullyParallel:false,workers:1,
 use:{baseURL:"http://127.0.0.1:4340",channel:"chrome",headless:true,trace:"retain-on-failure"},
 webServer:{command:`npm run build && "${resolve(process.platform==="win32"?"../.venv/Scripts/python.exe":"../.venv/bin/python")}" tests/browser_server.py "${join(mkdtempSync(join(tmpdir(),"pramaan-rc-browser-")),"ledger.sqlite")}" --port 4340`,url:"http://127.0.0.1:4340",reuseExistingServer:false,timeout:120000}
});
