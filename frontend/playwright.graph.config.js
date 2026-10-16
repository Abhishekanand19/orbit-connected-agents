import {defineConfig} from '@playwright/test';
import path from 'node:path';
const root=path.resolve('..');
const python=process.platform==='win32'?path.join(root,'.venv/Scripts/python.exe'):path.join(root,'.venv/bin/python');
const graph=`orbit_test_visuals_${process.pid}_${Date.now()}`;
export default defineConfig({testDir:'./src',testMatch:'graph.spec.js',workers:1,timeout:45000,reporter:'list',
  globalTeardown:'./src/graph-test-teardown.js',metadata:{graph,python,root},
  use:{browserName:'chromium',channel:'msedge',viewport:{width:1920,height:1080},baseURL:'http://127.0.0.1:5174'},
  webServer:[
    {command:`"${python}" tests/orbit/graph_fixture.py --graph ${graph}`,cwd:root,url:'http://127.0.0.1:8002/api/health',timeout:30000,reuseExistingServer:false},
    {command:'npm run dev -- --port 5174 --strictPort',url:'http://127.0.0.1:5174',env:{VITE_ORBIT_API_URL:'http://127.0.0.1:8002'},reuseExistingServer:false}
  ]});
