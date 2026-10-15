import {test} from 'node:test';
import assert from 'node:assert/strict';
import {freshWorkspace,loadWorkspace,saveWorkspace,STORAGE_KEY} from './services.js';
test('workspace round trip keeps bot settings and independent conversations',()=>{
 const map=new Map();const storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};
 const data=freshWorkspace();data.selectedId='planner';data.bots[1].notifications=true;data.conversations.planner=[{id:'1',role:'user',content:'hello',createdAt:1}];
 assert.equal(saveWorkspace(storage,data),'');assert.deepEqual(loadWorkspace(storage).data,data);
});
test('corrupt data is preserved and storage errors are visible',()=>{
 const storage={getItem:()=>'{bad',setItem:()=>{throw Error('quota');}};
 assert.equal(loadWorkspace(storage).blocked,true);assert.match(saveWorkspace(storage,freshWorkspace()),/unavailable or full/);
 assert.equal(STORAGE_KEY,'orbit.workspace.v1');
});
