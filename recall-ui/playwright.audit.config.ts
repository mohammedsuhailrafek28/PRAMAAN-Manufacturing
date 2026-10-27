import {defineConfig} from "@playwright/test";
export default defineConfig({testDir:"tests/e2e",testMatch:/independent-audit\.spec\.ts/,timeout:30000,fullyParallel:false,workers:1,use:{channel:"chrome",headless:true,trace:"retain-on-failure"}});
