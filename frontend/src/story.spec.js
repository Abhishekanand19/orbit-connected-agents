import {test,expect} from '@playwright/test';
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('orbit.onboarding.complete.v1','true'));});
const inputs=[
 "Hey bro, my parents and my sister are coming together this weekend for my dad's post-surgery care.",
 "Yeah buddy, help me make the arrangements. Dad has a hospital appointment on Monday at 11 AM. Can you book an Uber for 9:45 AM?",
 "From PES University, Bengaluru, to Manipal Hospital, Jayanagar.",
 "One more thing. Mom's busy after 12:30 PM, I've got a team meeting at 2:30 PM, and Dad has physiotherapy at 4 PM.",
 "Hey, I saw a WhatsApp message saying hospitals are closed because of the ongoing student protests. Can you check whether Manipal Hospital, Jayanagar is actually closed?",
 "Hey, I just got an email from the hospital. Dad's Monday appointment has been moved from 11 AM to 1:45 PM. I'm a bit confused now. Can you help me figure things out?",
 "Okay, Priya said she can take Dad to the hospital on Monday. Can you update the plan and email her about the changes?",
 "Hey buddy, remember Dad's hospital appointment? The hospital now says he can attend Monday's 1:45 PM appointment over video. What changes in our plan?"
];
async function say(page,text){
 const start=Date.now();
 await page.getByRole('textbox',{name:'Message',exact:true}).fill(text);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Send message'}).click();const data=await(await response).json();
 expect(data.mode,JSON.stringify(data)).toBe('deterministic');expect(data.clarifications).toEqual([]);
 await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('');await expect(page.locator('.message.assistant').last().locator('[data-streaming=true]')).toHaveCount(0,{timeout:20000});await expect(page.locator('.specialist-typing')).toHaveCount(0,{timeout:20000});console.log('TIMING',JSON.stringify({intents:data.intents,backend_ms:data.latency_ms,presentation_ms:Date.now()-start}));return data;
}
async function state(page,key){return page.evaluate(async key=>{const r=await fetch('http://127.0.0.1:8002/api/story/state',{headers:{'X-Orbit-Story':key||sessionStorage.getItem('orbit.story.workspace')}});return r.json();},key);}
async function ready(page){await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();}

test('seven-part story, New Chat memory, checklist and two hard-refresh regressions',async({page},info)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await ready(page);expect((await state(page)).graph.nodes).toEqual([]);
 let first;for(let i=0;i<7;i++){if(i===6)await page.evaluate(()=>{window.reveals=[];const seen=new WeakSet();window.observer=new MutationObserver(()=>{document.querySelectorAll('.inline-handoff').forEach(e=>{if(!seen.has(e)){seen.add(e);window.reveals.push(performance.now());}});});document.querySelectorAll('.inline-handoff').forEach(e=>seen.add(e));window.observer.observe(document.querySelector('[role=log]'),{childList:true,subtree:true});});const r=await say(page,inputs[i]);if(i===6){const times=await page.evaluate(()=>{window.observer.disconnect();return window.reveals;});expect(times).toHaveLength(3);expect(times[1]-times[0]).toBeGreaterThan(200);expect(times[2]-times[1]).toBeGreaterThan(200);console.log('HANDOFF_GAPS_MS',times[1]-times[0],times[2]-times[1]);}if(i===1){await expect(page.locator('.route-preview')).toHaveCount(0);await expect(page.getByRole('log')).toContainText('1. Where should the cab pick you up?');}if(i===2){
   const preview=page.locator('.message.assistant').last().getByRole('button',{name:'Enlarge route preview'});await expect(preview).toBeVisible();
   await preview.click();await expect(page.getByRole('dialog',{name:'Enlarged route preview'})).toBeVisible();
   await page.screenshot({path:info.outputPath('route-enlarged.png')});await page.getByRole('button',{name:'Close preview'}).click();
  }
  if(i===4){await expect(page.locator('.research-citations a')).toHaveCount(1);await expect(page.locator('.research-citations a').first()).toHaveAttribute('href','https://economictimes.indiatimes.com/topic/cjp-protest');}
  if(i===2){
   expect(r.direct_specialist).toBe(true);await expect(page.locator('.message.assistant').last().locator('.handoff-label')).toHaveCount(0);await expect(page.locator('.route-preview')).toHaveCount(1);expect(r.graph.nodes.find(n=>n.id==='story:hospital').properties.name).toBe('Manipal Hospital, Jayanagar');
   await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
   const panel=page.getByRole('region',{name:'Graph exploration workspace'});
   await expect(panel.getByTestId('graph-canvas')).toContainText('Manipal Hospital, Jayanagar');
   await page.screenshot({path:info.outputPath('hospital-network.png')});
   await panel.getByRole('button',{name:'Simple View',exact:true}).click();
   await expect(panel.getByTestId('simple-explanation')).toContainText('Manipal Hospital, Jayanagar');
   await page.screenshot({path:info.outputPath('hospital-simple.png')});
   await panel.getByRole('button',{name:'Close graph workspace'}).click();
  }
  if(i===0){first=r;expect(r.graph.nodes.filter(n=>n.type==='Person')).toHaveLength(3);}}
 await expect(page.getByRole('log')).toContainText("What's Priya's email address?");
 await say(page,'Her email is priya@example.com.');await expect(page.getByRole('button',{name:'Approve exact action'})).toHaveCount(1);
 await expect(page.getByRole('log')).not.toContainText('Email sent to Priya');
 await page.getByRole('button',{name:'Approve exact action'}).scrollIntoViewIfNeeded();await page.screenshot({animations:'disabled',path:info.outputPath('part6-approval.png')});
 const run=await page.evaluate(()=>sessionStorage.getItem('orbit.story.workspace'));
 await page.getByRole('button',{name:'New Chat',exact:true}).click();await expect(page.locator('.message')).toHaveCount(0);
 expect(await page.evaluate(()=>sessionStorage.getItem('orbit.story.workspace'))).toBe(run);
 const video=await say(page,inputs[7]);expect(video.previous.length).toBeGreaterThan(0);
 await expect(page.getByRole('log')).toContainText('Of course, I remember.');
 const check=page.getByRole('checkbox',{name:/Confirm video joining details with the hospital/});await check.click();await expect(check).toBeChecked();
 expect((await state(page)).graph.nodes.find(n=>n.id==='story:checklist:joining').properties.evidence_status).toBe('USER_REPORTED');
 await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
 const graph=page.getByRole('region',{name:'Graph exploration workspace'});await expect(graph.getByTestId('graph-canvas')).toBeVisible();
 await page.screenshot({animations:'disabled',path:info.outputPath('part7-network.png')});
 await graph.getByRole('button',{name:'Simple View',exact:true}).click();await expect(graph.getByTestId('simple-explanation')).toBeVisible();
 await expect(graph.getByTestId('simple-explanation')).toContainText('Your linked checklist');
 await expect(graph.getByTestId('simple-explanation')).toContainText('User-reported complete');
 await page.screenshot({animations:'disabled',path:info.outputPath('part7-simple.png')});
 const cdp=await page.context().newCDPSession(page);
 for(let iteration=0;iteration<2;iteration++){
  const prior=await page.evaluate(()=>sessionStorage.getItem('orbit.story.workspace'));
  await cdp.send('Page.reload',{ignoreCache:true});await ready(page);
  await expect(page.locator('.message')).toHaveCount(0);await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('');
  expect(await page.evaluate(()=>sessionStorage.getItem('orbit.story.workspace'))).not.toBe(prior);
  expect((await state(page)).graph.nodes).toEqual([]);expect((await state(page,prior)).graph.nodes.length).toBeGreaterThan(0);
  const intro=await say(page,inputs[0]);expect(intro.assistant.properties.content).toBe(first.assistant.properties.content);expect(intro.handoffs).toEqual([]);
  await expect(page.locator('.message.user')).toHaveCount(1);await expect(page.locator('.message.assistant')).toHaveCount(1);
  await expect(page.getByRole('log')).not.toContainText('video consultation');await expect(page.getByRole('log')).not.toContainText('1:45 PM');
  if(iteration===0)for(const text of inputs.slice(1,4))await say(page,text);
 }
 await page.screenshot({animations:'disabled',path:info.outputPath('refreshed-introduction.png')});expect(errors).toEqual([]);
});

test('workspace menu repeats existing onboarding without revoking connectors',async({page})=>{
 await page.goto('/');await ready(page);
 for(let i=0;i<2;i++){
  await page.getByRole('button',{name:'Abhishek Anand workspace menu'}).click();
  await page.getByRole('menuitem',{name:'Restart onboarding'}).click();
  await expect(page.getByRole('heading',{name:'Sign in — Orbit demo',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await page.getByRole('button',{name:'Continue to Orbit',exact:true}).click();await ready(page);
 }
 await page.reload();await ready(page);await expect(page.getByRole('heading',{name:'Welcome to Orbit',exact:true})).toHaveCount(0);
});

test('normal-mode reload retains conversation and does not create story runs',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('orbit.chat.mode','normal'));
 let creations=0;page.on('request',r=>{if(r.url().endsWith('/api/story/workspaces'))creations++;});
 await page.route('**/api/chat/bots/coordinator/latest',r=>r.fulfill({json:{conversation_id:'normal:saved',messages:[{id:'normal:msg',created_at:1,properties:{role:'assistant',content:'Existing normal conversation'}}]}}));
 await page.goto('/');await expect(page.getByRole('log')).toContainText('Existing normal conversation');
 await page.reload();await expect(page.getByRole('log')).toContainText('Existing normal conversation');expect(creations).toBe(0);
});
