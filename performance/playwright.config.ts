// Test-only isolation: inherit the frozen pinned CI config and all original assertions.
// Another agent owns4173; do not stop or reuse it. No product timeout changes.
import {defineConfig} from '../recall-ui/node_modules/@playwright/test/index.mjs';
import base from '../ci/playwright.config';
const server=base.webServer as {command:string};
export default defineConfig({...base,
 use:{...base.use,baseURL:'http://127.0.0.1:4450'},
 webServer:{...server,command:server.command+' --port 4450',url:'http://127.0.0.1:4450',reuseExistingServer:false}
});
