import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests/reliability',workers:1,timeout:180000,
 use:{channel:'chrome',headless:true},reporter:'list'});
