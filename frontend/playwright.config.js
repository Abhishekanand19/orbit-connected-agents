import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./src',testMatch:'**/*.spec.js',use:{browserName:'chromium',channel:'msedge',viewport:{width:1440,height:1000}},workers:1,reporter:'list'});
