import {execFileSync} from 'node:child_process';
import {test,expect} from '@playwright/test';
const api='http://127.0.0.1:8002';
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('orbit.chat.mode','normal'));});
async function open(page,mode='Graph') {
 await page.goto('/');await page.getByRole('button',{name:`Open ${mode} View`,exact:true}).click();
 await page.getByRole('button',{name:'Explore Hospital appointment',exact:true}).click();
 await expect(page.locator('[data-entity-id="sample:appointment"]')).toBeVisible();
 await expect(page.getByTestId('graph-canvas')).toBeVisible();
}
async function ids(page,attribute) {return page.locator(`[${attribute}]`).evaluateAll((items,a)=>items.map(n=>n.getAttribute(a)).sort(),attribute);}
test('both modes preserve API entities, directions, cross-links and details',async({page,request})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await open(page);
 await page.getByRole('button',{name:'3 hops',exact:true}).click();
 const response=await request.post(api+'/api/graph/subgraph',{data:{root_id:'sample:appointment',hops:3,direction:'both',limit:100}});
 expect(response.ok()).toBeTruthy();const graph=await response.json();
 await expect.poll(()=>ids(page,'data-entity-id')).toEqual(graph.nodes.map(n=>n.id).sort());
 await expect.poll(()=>ids(page,'data-edge-id')).toEqual(graph.edges.map(e=>e.id).sort());
 await page.screenshot({path:'test-results/orbit-graph-1920.png'});
 await page.getByRole('button',{name:'Simple View',exact:true}).click();
 await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-mode','simple');
 await expect.poll(()=>ids(page,'data-entity-id')).toEqual(graph.nodes.map(n=>n.id).sort());
 await expect.poll(()=>ids(page,'data-edge-id')).toEqual(graph.edges.map(e=>e.id).sort());
 expect(await page.locator('.cross-link').count()).toBeGreaterThan(0);
 const root=await page.locator('[data-entity-id="sample:appointment"]').boundingBox();
 for(const n of graph.nodes.filter(n=>n.id!=='sample:appointment')){
   const b=await page.locator(`[data-entity-id="${n.id}"]`).boundingBox();expect(b.y).toBeGreaterThan(root.y);
 }
 const edge=graph.edges.find(e=>e.source==='sample:transport'&&e.type==='ASSIGNED_TO');
 await page.locator(`[data-edge-id="${edge.id}"]`).click();
 await expect(page.locator('.graph-inspector')).toContainText('ASSIGNED_TO');
 await expect(page.locator('.edge-direction')).toContainText('Transport booking');
 await expect(page.locator('.edge-direction')).toContainText('Priya');
 await page.locator('[data-entity-id="sample:claim"]').click();
 await expect(page.locator('.graph-inspector')).toContainText('PENDING');
 await expect(page.locator('.graph-inspector')).toContainText('Evidence & mentions');
 await page.screenshot({path:'test-results/orbit-simple-1920.png'});
 await page.getByRole('button',{name:'Collapse Hospital appointment',exact:true}).click();
 await expect(page.locator('[data-entity-id]')).toHaveCount(1);
 await page.getByRole('button',{name:'Expand Hospital appointment',exact:true}).click();
 await expect.poll(()=>ids(page,'data-entity-id')).toEqual(graph.nodes.map(n=>n.id).sort());
 await page.getByRole('button',{name:'Close graph workspace'}).click();
 await expect(page.getByLabel('Message',{exact:true})).toBeVisible();
 expect(errors).toEqual([]);
});
test('actual backend mutations refresh in both modes and on reopening',async({page,request})=>{
 await open(page);
 const graph=await (await request.post(api+'/api/graph/subgraph',{data:{root_id:'sample:appointment',hops:2}})).json();
 const old=graph.edges.find(e=>e.source==='sample:transport'&&e.type==='ASSIGNED_TO');
 try {
  expect((await request.delete(api+'/api/relationships/'+old.id)).ok()).toBeTruthy();
  const added=await request.put(api+'/api/relationships',{data:{source:'sample:transport',type:'ASSIGNED_TO',target:'sample:dad'}});expect(added.ok()).toBeTruthy();const newEdge=await added.json();
  await page.getByRole('button',{name:'Refresh graph'}).click();
  await expect(page.locator(`[data-edge-id="${old.id}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-edge-id="${newEdge.id}"]`)).toBeVisible();
  await page.getByRole('button',{name:'Simple View',exact:true}).click();
  await expect(page.locator(`[data-edge-id="${newEdge.id}"]`)).toBeVisible();
  await page.getByRole('button',{name:'Close graph workspace'}).click();
  await page.getByRole('button',{name:'Open Simple View',exact:true}).click();
  await expect(page.locator(`[data-edge-id="${newEdge.id}"]`)).toBeVisible();
  await request.delete(api+'/api/relationships/'+newEdge.id);
 } finally {await request.put(api+'/api/relationships',{data:{source:old.source,type:old.type,target:old.target}});}
});
test('search, filters, zoom, drag, focus and stale-request cancellation',async({page,request})=>{
 await open(page);
 await page.getByLabel('Search graph entities').fill('priya');
 await expect(page.locator('.entity-result')).toHaveCount(3); // Person, claim and message all mention Priya.
 await page.getByRole('button',{name:'Explore Priya',exact:true}).click();
 await expect(page.locator('.graph-breadcrumb')).toContainText('Priya');
 await page.getByLabel('Filter entity type').selectOption('Person');
 await expect(page.locator('[data-entity-id] .entity-type')).toHaveText(['Person · FOCUS']);
 await page.getByLabel('Filter entity type').selectOption('');
 await page.getByLabel('Search graph entities').fill('');
 await expect(page.locator('[data-entity-id]')).not.toHaveCount(1);
 const viewport=page.locator('.react-flow__viewport');const before=await viewport.getAttribute('style');
 await page.getByRole('button',{name:'Zoom In',exact:true}).click();
 await expect.poll(()=>viewport.getAttribute('style')).not.toBe(before);
 await page.getByRole('button',{name:'Fit View',exact:true}).click();
 const n=page.locator('[data-entity-id="sample:priya"]');const bounds=await n.boundingBox();
 await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);await page.mouse.down();await page.mouse.move(bounds.x+bounds.width/2+60,bounds.y+bounds.height/2+40,{steps:8});await page.mouse.up();
 const after=await n.boundingBox();expect(Math.abs(after.x-bounds.x)).toBeGreaterThan(20);
 await n.click();await page.getByRole('button',{name:'Explore from here'}).click();
 await expect(page.locator('.graph-breadcrumb')).toContainText('Priya');
 await page.getByRole('button',{name:'4 hops',exact:true}).click();await page.getByRole('button',{name:'1 hop',exact:true}).click();
 await expect(page.getByRole('button',{name:'1 hop',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByTestId('graph-canvas')).toBeVisible();
 const latest=await (await request.post(api+'/api/graph/subgraph',{data:{root_id:'sample:priya',hops:1,direction:'both',limit:100}})).json();
 await expect.poll(()=>ids(page,'data-entity-id')).toEqual(latest.nodes.map(n=>n.id).sort());
});
test('network errors show no fake or stale graph, then recover',async({page})=>{
 await open(page);
 await page.route('**/api/graph/subgraph',route=>route.abort('connectionrefused'));
 await page.getByRole('button',{name:'Refresh graph'}).click();
 await expect(page.getByRole('heading',{name:'Connection interrupted.'})).toBeVisible();
 await expect(page.locator('[data-entity-id]')).toHaveCount(0);
 await page.unroute('**/api/graph/subgraph');await page.getByRole('button',{name:'Try again',exact:true}).click();
 await expect(page.getByTestId('graph-canvas')).toBeVisible();
});
test('mobile workspace closes back to intact chat',async({page})=>{
 await page.setViewportSize({width:390,height:844});await open(page,'Simple');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-mode','simple');
 await page.screenshot({path:'test-results/orbit-graph-mobile.png'});
 await page.getByRole('button',{name:'Close graph workspace'}).click();
 await page.getByLabel('Message',{exact:true}).fill('Chat stays intact');await page.getByLabel('Message',{exact:true}).press('Enter');
 await expect(page.locator('.message-bubble')).toHaveText('Chat stays intact');
});

test('empty real graph has an honest empty state',async({page,request},testInfo)=>{
 const {graph,python,root}=testInfo.config.metadata;
 const health=await (await request.get(api+'/api/health')).json();
 expect(health.graph).toBe(graph);
 execFileSync(python,['tests/orbit/graph_fixture.py','--graph',graph,'--empty'],{cwd:root});
 await page.goto('/');await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
 await expect(page.getByText('This graph is empty. Add entities through the backend to begin.')).toBeVisible();
 await expect(page.locator('[data-entity-id]')).toHaveCount(0);
 await expect(page.locator('[data-edge-id]')).toHaveCount(0);
});

test('live chat extraction appears in both graph views and survives reload',async({page,request})=>{
 test.setTimeout(150000);
 await page.goto('/');
 await page.getByLabel('Message',{exact:true}).fill('My colleague Celia Veridian might review my proposal on Friday.');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 await expect(page.locator('.message.assistant .message-bubble')).toBeVisible({timeout:120000});
 const reply=await page.locator('.message.assistant .message-bubble').innerText();expect(reply.length).toBeGreaterThan(10);
 await page.reload();await expect(page.locator('.message.assistant .message-bubble')).toHaveText(reply);
 await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
 await page.getByLabel('Search graph entities').fill('Celia Veridian');
 await page.getByRole('button',{name:'Explore Celia Veridian',exact:true}).click();
 const directory=await (await request.get(api+'/api/nodes?q=Celia%20Veridian')).json();
 const person=directory.items.find(n=>n.type==='Person');expect(person).toBeTruthy();
 for(const mode of ['Graph View','Simple View']){
  await page.getByRole('button',{name:mode,exact:true}).click();
  await page.getByRole('button',{name:'Refresh graph'}).click();
  const graph=await (await request.post(api+'/api/graph/subgraph',{data:{root_id:person.id,hops:2,direction:'both',limit:100}})).json();
  expect(graph.nodes.some(n=>n.type==='Claim'&&n.properties.status==='PENDING')).toBeTruthy();
  expect(graph.edges.length).toBeGreaterThan(0);
  await expect.poll(()=>ids(page,'data-entity-id')).toEqual(graph.nodes.map(n=>n.id).sort());
  await expect.poll(()=>ids(page,'data-edge-id')).toEqual(graph.edges.map(e=>e.id).sort());
 }
});
