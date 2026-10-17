import {test,expect} from '@playwright/test';
test('original workspace eight-stage visual acceptance',async({page},testInfo)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'Orbit Coordinator'})).toBeVisible();
 await expect(page.getByRole('navigation',{name:'Your bots'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Start deterministic family demo'})).toHaveCount(0);
 await page.screenshot({path:testInfo.outputPath('workspace.png')});
 await page.getByRole('button',{name:'Toggle bot settings'}).click();await expect(page.getByLabel('Conversation engine')).toBeVisible();await page.getByRole('button',{name:'Close settings'}).click();
 const timings=[],results=[];
 async function say(text){const started=Date.now();await page.getByRole('textbox',{name:'Message',exact:true}).fill(text);const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');await page.getByRole('button',{name:'Send message'}).click();const data=await(await response).json();expect(data.mode,JSON.stringify(data)).toBe('deterministic');expect(data.clarifications).toEqual([]);await expect(page.getByRole('button',{name:'Send message'})).toBeDisabled();results.push(data);timings.push(Date.now()-started);return data;}
 async function views(stage){
  await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Graph exploration workspace'});await expect(dialog.getByTestId('graph-canvas')).toBeVisible();
  await expect(dialog.locator('.entity-node.network').first()).toBeVisible();
  await expect.poll(async()=>dialog.locator('[data-entity-id]').evaluateAll(nodes=>{const boxes=nodes.map(n=>n.getBoundingClientRect());return boxes.every((a,i)=>boxes.every((b,j)=>i===j||Math.hypot(a.x+a.width/2-b.x-b.width/2,a.y+a.height/2-b.y-b.height/2)>(a.width+b.width)/2-2));})).toBe(true);
  if(stage===1){await dialog.getByLabel('Graph context').selectOption('people');await expect(dialog.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');await expect(dialog.getByTestId('graph-canvas')).toHaveAttribute('data-edge-count','2');}
  await dialog.getByRole('button',{name:'Fit View',exact:true}).click();
  await page.evaluate(()=>new Promise(resolve=>{let last='',stable=0,frames=0;function frame(){const transform=document.querySelector('.react-flow__viewport')?.getAttribute('style')||'';stable=transform===last?stable+1:0;last=transform;if(stable>=5||frames++>120)resolve(null);else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
  await page.screenshot({path:testInfo.outputPath(`stage${stage}-network.png`),animations:'disabled'});
  await dialog.getByRole('button',{name:'Simple View',exact:true}).click();await expect(dialog.getByTestId('simple-explanation')).toBeVisible();
  await page.screenshot({path:testInfo.outputPath(`stage${stage}-simple.png`),animations:'disabled'});
  if(stage>=5)await expect(dialog.getByTestId('simple-explanation')).toContainText('1:45');
  await dialog.getByRole('button',{name:'Close graph workspace'}).click();
 }
 const inputs=["Hey Orbit, I'm Aarav. My dad is Ramesh and Priya is my sister.","Dad has a follow-up at 11 tomorrow. Mom Meera is taking him, and the cab arrives at 9:45.","Mom is busy after 12:30, Priya is free from noon, my deployment is at 2:30, and Dad has physio at 4.","Someone forwarded a message saying the hospital is closed because of a protest. Should I cancel the cab?","The hospital emailed me that Dad's appointment moved from 11 to 1:45. What does that affect?","Priya confirmed she can take Dad. Can you organize everything and tell everyone?","Hey Orbit, remember Dad's appointment? The hospital says he can do it over video now. Do we still need the cab?","Perfect, where do things stand now?"];
 await say(inputs[0]);await views(1);await say(inputs[1]);await views(2);await say(inputs[2]);await views(3);await say(inputs[3]);await views(4);await expect(page.getByRole('log')).toContainText('Research Assistant');await say(inputs[4]);await views(5);
 const sixth=await say(inputs[5]);await views(6);expect(sixth.handoffs.map(h=>h.agent)).toEqual(['planner','tasks','communication']);await page.getByRole('button',{name:'Approve exact action',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:testInfo.outputPath('inline-approval.png')});
 await page.getByRole('button',{name:'Why?',exact:true}).last().click();await expect(page.getByRole('dialog',{name:'Why did Orbit do this?'})).toContainText('WAITING');await page.getByRole('button',{name:'Close explanation'}).click();
 const approve=page.getByRole('button',{name:'Approve exact action',exact:true});await expect(approve).toHaveCount(1);await approve.click();await expect(page.getByRole('log')).toContainText('Verified by fresh readback');
 const oldConversation=sixth.user.properties.conversation_id;
 const newResponse=page.waitForResponse(r=>r.url().endsWith('/api/story/conversations'));await page.getByRole('button',{name:'New Chat',exact:true}).click();const newId=(await(await newResponse).json()).id;expect(newId).not.toBe(oldConversation);
 await expect(page.locator('.message')).toHaveCount(0);await page.screenshot({animations:'disabled',path:testInfo.outputPath('new-chat.png')});
 await page.reload();await expect(page.locator('.message')).toHaveCount(0);
 const seventh=await say(inputs[6]);expect(seventh.previous.length).toBeGreaterThan(0);await expect(page.getByRole('log')).toContainText('1:45 PM');await page.locator('.message.assistant').last().scrollIntoViewIfNeeded();await page.screenshot({path:testInfo.outputPath('cross-session.png')});await views(7);
 await expect(approve).toHaveCount(1);await approve.click();await expect(page.getByRole('log')).toContainText('Verified by fresh readback');await say(inputs[7]);await views(8);await expect(page.getByRole('log')).toContainText('removed after approval and verified readback');
 await page.reload();await expect(page.getByRole('log')).toContainText('removed after approval and verified readback');expect(errors).toEqual([]);
 console.log(JSON.stringify({chat_roundtrip_ms:timings,stages:results.map(r=>({intents:r.intents,revision:r.graph_revision}))}));
});
