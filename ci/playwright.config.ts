/** CI-only browser selection; the frozen product/test config is unchanged. */
import { defineConfig } from '../recall-ui/node_modules/@playwright/test/index.mjs';
import base from '../recall-ui/playwright.config';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
if(!process.env.PRAMAAN_CI_CHROME)throw new Error('Pinned CI Chrome executable is required');
export default defineConfig({
 ...base,
 testDir:resolve(root,'recall-ui/tests/e2e'),
 // Serial on hosted runners: the suite starts many owned server processes and the UI's 4 s request limit is deliberately not raised,
 // so parallel workers on a small runner produced load timeouts that say nothing about the product. Assertions and counts are unchanged.
 fullyParallel:false,workers:1,
 outputDir:resolve(root,'.tmp-ci-results/browser-traces'),
 use:{...base.use,channel:undefined,launchOptions:{executablePath:process.env.PRAMAAN_CI_CHROME}},
 webServer:{...(base.webServer as object),cwd:resolve(root,'recall-ui')},
});
