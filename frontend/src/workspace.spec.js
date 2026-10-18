import {test,expect} from '@playwright/test';
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('orbit.onboarding.complete.v1','true'));});
const family="Hey Orbit, I'm Aarav. My dad is Ramesh and Priya is my sister.";
async function ready(page){await page.goto('/');await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();}
async function say(page,text){await page.getByRole('textbox',{name:'Message',exact:true}).fill(text);const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');await page.getByRole('button',{name:'Send message'}).click();const result=await(await response).json();expect(result.error).toBeUndefined();await expect(page.getByRole('button',{name:'Send message'})).toBeDisabled();return result;}
test('workspace controls, attribution, dock and conversation graph scope',async({page},info)=>{
 await ready(page);await page.screenshot({animations:'disabled',path:info.outputPath('expanded.png')});
 await page.getByRole('button',{name:'Collapse sidebar'}).click();await expect(page.locator('.app')).toHaveClass(/rail/);await expect.poll(async()=>(await page.locator('.sidebar').boundingBox()).width).toBeLessThan(80);await page.screenshot({animations:'disabled',path:info.outputPath('collapsed.png')});await page.reload();await expect(page.locator('.app')).toHaveClass(/rail/);await page.getByRole('button',{name:'Expand sidebar'}).click();
 await page.getByRole('button',{name:'Toggle bot settings'}).click();await expect(page.getByLabel('Name',{exact:true})).toHaveValue('Coordinator');await page.getByRole('button',{name:'Close settings'}).click();await expect(page.locator('.settings')).toHaveCount(0);
 await page.getByRole('button',{name:'Toggle bot settings'}).click();await page.getByRole('textbox',{name:'Purpose',exact:true}).fill('Keep my family plan connected.');await page.getByRole('button',{name:'Close settings'}).click();await page.reload();await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();await page.getByRole('button',{name:'Toggle bot settings'}).click();await expect(page.getByRole('textbox',{name:'Purpose',exact:true})).toHaveValue('Keep my family plan connected.');await page.getByRole('button',{name:'Close settings'}).click();
 await expect(page.getByText('Deterministic planning',{exact:false})).toHaveCount(0);
 await page.getByRole('button',{name:'Open Graph View'}).click();const graph=page.getByRole('region',{name:'Graph exploration workspace'});await expect(graph).toContainText('Your connections will appear here as you chat.');
 const first=await say(page,family);await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-edge-count','2');await expect(page.locator('.bot-identity').first()).toHaveText('@ Coordinator');
 await page.screenshot({animations:'disabled',path:info.outputPath('docked-stage1.png')});const chatBox=await page.locator('.chat').boundingBox(),graphBox=await graph.boundingBox();expect(graphBox.x).toBeGreaterThanOrEqual(chatBox.x+chatBox.width-1);
 await page.getByRole('textbox',{name:'Message',exact:true}).fill('Draft stays here');await page.getByRole('button',{name:'Open Simple View'}).click();await expect(page.getByTestId('simple-explanation')).toBeVisible();await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('Draft stays here');await page.screenshot({animations:'disabled',path:info.outputPath('docked-simple.png')});
 await page.getByRole('button',{name:'New Chat',exact:true}).click();await expect(graph).toContainText('Your connections will appear here as you chat.');await page.screenshot({animations:'disabled',path:info.outputPath('new-chat-empty-memory-preserved.png')});
 const remembered=await say(page,'Remember Dad and Priya?');expect(remembered.graph.nodes.some(n=>n.id==='story:ramesh')).toBe(true);await expect(page.getByTestId('simple-explanation')).toContainText('Ramesh');
 await page.getByRole('button',{name:'Close graph workspace'}).click();expect((await page.locator('.chat').boundingBox()).width).toBeGreaterThan(chatBox.width);
});
test('real text/image upload, removal and persistent attachment preview',async({page},info)=>{
 await ready(page);const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Attach file or image'}).click();await(await chooser).setFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('A harmless note for this conversation. No actions requested.')});
 await expect(page.locator('.attachment-chip')).toContainText('notes.txt');await page.getByRole('button',{name:'Preview text',exact:true}).click();await expect(page.locator('.file-preview')).toContainText('A harmless note');await page.getByRole('button',{name:'Use text in composer'}).click();await expect(page.getByRole('textbox',{name:'Message',exact:true})).toContainText('A harmless note');await page.screenshot({animations:'disabled',path:info.outputPath('attachment-selected.png')});await page.getByRole('button',{name:'Remove notes.txt'}).click();await expect(page.locator('.attachment-chip')).toHaveCount(0);
 await page.locator('input[type=file]').setInputFiles({name:'notes.txt',mimeType:'text/plain',buffer:Buffer.from('A harmless note for this conversation. No actions requested.')});
 await page.locator('input[type=file]').setInputFiles({name:'pixel.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jQ1sAAAAASUVORK5CYII=','base64')});await say(page,family);await expect(page.locator('.message-attachment').filter({hasText:'pixel.png'})).toContainText('Stored only; no OCR or analysis');await expect(page.locator('.message-attachment').filter({hasText:'notes.txt'})).toContainText('notes.txt');await page.locator('.message-attachment').filter({hasText:'notes.txt'}).locator('summary').click();await expect(page.locator('.message-attachment pre')).toContainText('A harmless note');await page.reload();await expect(page.locator('.message-attachment')).toHaveCount(0);await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();
 await page.locator('input[type=file]').setInputFiles({name:'unsafe.exe',mimeType:'application/octet-stream',buffer:Buffer.from('bad')});await expect(page.getByRole('alert')).toContainText('Supported files');
});
test('unsupported speech shows actionable fallback',async({page})=>{
 await page.addInitScript(()=>{window.SpeechRecognition=undefined;window.webkitSpeechRecognition=undefined;});await ready(page);await page.getByRole('button',{name:'Start microphone'}).click();await expect(page.getByRole('alert')).toContainText('unavailable in this browser');await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeEditable();
});
test('native browser speech availability probe (not spoken transcription verification)',async({page},info)=>{
 await ready(page);await page.getByRole('button',{name:'Start microphone'}).click();await expect(page.locator('.voice-input')).toContainText(/listening|requesting|Allow|unavailable|connect|Microphone|microphone/i);await page.screenshot({animations:'disabled',path:info.outputPath('native-microphone.png')});console.log('NATIVE SPEECH PROBE:',await page.locator('.voice-input').innerText());if(await page.getByRole('button',{name:'Cancel',exact:true}).count())await page.getByRole('button',{name:'Cancel',exact:true}).click();
});


test('drag both dock edges, persist widths, preserve controls and render streamed text',async({page},info)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await ready(page);
 async function drag(label,dx){const box=await page.getByRole('separator',{name:label}).boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+dx,box.y+box.height/2,{steps:12});await page.mouse.up();}
 const width=selector=>page.locator(selector).evaluate(e=>Math.round(e.getBoundingClientRect().width));
 await drag('Resize bot sidebar',60);expect(await width('.sidebar')).toBe(320);
 await page.getByRole('button',{name:'Open Graph View'}).click();await expect(page.getByRole('region',{name:'Graph exploration workspace'})).toBeVisible();
 await drag('Resize graph sidebar',-150);expect(await width('.graph-dock')).toBe(670);
 await drag('Resize graph sidebar',70);expect(await width('.graph-dock')).toBe(600);
 await page.getByRole('button',{name:'Collapse sidebar'}).click();await expect.poll(()=>width('.sidebar')).toBeLessThan(80);
 await page.getByRole('button',{name:'Expand sidebar'}).click();await expect.poll(()=>width('.sidebar')).toBe(320);
 await page.reload();await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();expect(await width('.sidebar')).toBe(320);
 await page.getByRole('button',{name:'Open Graph View'}).click();expect(await width('.graph-dock')).toBe(600);
 const result=await say(page,family),full=result.assistant.properties.content;
 const text=page.locator('.message.assistant .message-bubble .streaming-text');await expect(text).toHaveAttribute('data-streaming','true');expect((await text.innerText()).length).toBeLessThan(full.length);
 await expect(text).toHaveAttribute('data-streaming','false',{timeout:15000});expect(await text.innerText()).toBe(full);
 await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');
 await drag('Resize graph sidebar',-100);await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');
 await page.setViewportSize({width:1280,height:800});await expect.poll(()=>page.locator('.chat').evaluate(e=>e.clientWidth)).toBeGreaterThanOrEqual(350);await expect.poll(()=>page.getByTestId('graph-canvas').evaluate(el=>{const b=el.getBoundingClientRect();return [...el.querySelectorAll('.react-flow__node')].every(n=>{const r=n.getBoundingClientRect();return r.left>=b.left&&r.right<=b.right&&r.top>=b.top&&r.bottom<=b.bottom;});})).toBe(true);await page.screenshot({animations:'disabled',path:info.outputPath('resized-live-graph.png')});
 await page.getByRole('button',{name:'Open Simple View'}).click();await expect(page.getByTestId('simple-explanation')).toBeVisible();await page.screenshot({animations:'disabled',path:info.outputPath('resized-simple.png')});
 await page.getByRole('button',{name:'Close graph workspace'}).click();await expect(page.locator('.graph-dock')).toHaveCount(0);expect(errors).toEqual([]);
});


test('all five agents stream formatted responses without provider calls',async({page},info)=>{
 await page.addInitScript(()=>localStorage.setItem('orbit.chat.mode','normal'));
 const text='**Recorded plan**\n\n1. [✅] This is the first recorded finding with its original spacing.\n2. [⏳] The next step awaits approval.\n3. [❌] Nothing has been sent.\n\n[Read the source](https://economictimes.indiatimes.com/topic/cjp-protest)';
 await page.route('**/api/chat/bots/*/latest',r=>{const id=r.request().url().split('/').at(-2);return r.fulfill({json:{conversation_id:'test:'+id,messages:[{id:'stream:'+id,created_at:1,properties:{role:'assistant',content:text}}]}});});
 await ready(page);
 for(const name of ['Coordinator','Planner','Researcher','Communication Assistant','Task Manager']){
  if(name!=='Coordinator')await page.getByRole('navigation',{name:'Your bots'}).getByRole('button',{name,exact:true}).click();
  const stream=page.locator('.message.assistant .streaming-text');await expect(stream).toHaveAttribute('data-streaming','true');await expect(stream.locator('a')).toHaveCount(0);
  const start=await stream.innerText();await expect.poll(()=>stream.innerText()).not.toBe(start);
  await expect(stream).toHaveAttribute('data-streaming','false',{timeout:15000});await expect(stream.locator('strong')).toHaveText('Recorded plan');await expect(stream.getByRole('link',{name:'Read the source'})).toHaveAttribute('href','https://economictimes.indiatimes.com/topic/cjp-protest');await expect(stream).toContainText('1. [✅]');await expect(stream).toContainText('2. [⏳]');await expect(stream).toContainText('3. [❌]');
 }
 await page.screenshot({path:info.outputPath('formatted-agent-response.png')});
});
