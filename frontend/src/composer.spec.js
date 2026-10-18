import {test,expect} from '@playwright/test';
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('orbit.onboarding.complete.v1','true'));});
test('compact composer, depth and actual microphone permission probe',async({page},info)=>{
 await page.goto('/');await expect(page.getByRole('textbox',{name:'Message',exact:true})).toBeVisible();
 const box=await page.locator('.composer').boundingBox();expect(box.height).toBeLessThan(80);
 await expect(page.getByText('Review your message before sending',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Private workspace',{exact:true})).toHaveCount(0);
 await page.getByLabel('Response depth').selectOption('low');await page.reload();await expect(page.getByLabel('Response depth')).toHaveValue('low');
 await page.screenshot({path:info.outputPath('compact.png'),animations:'disabled'});
 await page.getByRole('button',{name:'Start microphone'}).click();
 await expect.poll(()=>page.locator('.voice-input').innerText()).toMatch(/requesting|listening|Allow|microphone|unavailable|Speech/);
 await page.screenshot({path:info.outputPath('real-mic-probe.png'),animations:'disabled'});
 console.log('REAL MICROPHONE PROBE:',await page.locator('.voice-input').innerText());
 if(await page.getByRole('button',{name:'Cancel recording'}).count())await page.getByRole('button',{name:'Cancel recording'}).click({timeout:2000}).catch(async()=>{await expect(page.locator('.voice-input')).toHaveAttribute('data-voice-state','idle');});
 await page.setViewportSize({width:390,height:844});await expect(page.locator('.composer')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
 await page.screenshot({path:info.outputPath('compact-mobile.png'),animations:'disabled'});
});

test('persisted graph grows without remounting nodes or resetting the viewport',async({page},info)=>{
 await page.goto('/');await page.getByRole('button',{name:'Open Graph View',exact:true}).click();
 await expect(page.getByText('Your connections will appear here as you chat.')).toBeVisible();
 const say=async text=>{await page.getByRole('textbox',{name:'Message',exact:true}).fill(text);const response=page.waitForResponse(r=>r.url().endsWith('/api/chat')&&r.request().method()==='POST');await page.getByRole('button',{name:'Send message'}).click();const data=await(await response).json();expect(data.clarifications).toEqual([]);await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('');return data;};
 await say("My parents and sister are coming for dad's post-surgery care.");
 await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');
 await page.getByRole('button',{name:'Zoom Out',exact:true}).click();
 await page.evaluate(()=>{window.__person=document.querySelector('[data-entity-id="story:ramesh"]');window.__position=window.__person.closest('.react-flow__node').style.transform;});
 await page.getByRole('textbox',{name:'Message',exact:true}).fill('An unsent appointment at 11 AM');await expect(page.getByTestId('graph-canvas')).toHaveAttribute('data-node-count','3');
 const viewport=await page.locator('.react-flow__viewport').getAttribute('style');
 await say('Dad has a hospital appointment on Monday at 11 AM and an Uber at 9:45 AM.');
 await expect(page.locator('[data-entity-id="story:appointment"]').first()).toBeVisible();
 expect(await page.evaluate(()=>window.__person===document.querySelector('[data-entity-id="story:ramesh"]'))).toBe(true);
 expect(await page.evaluate(()=>document.querySelector('[data-entity-id="story:ramesh"]').closest('.react-flow__node').style.transform)).toBe(await page.evaluate(()=>window.__position));
 expect(await page.locator('.react-flow__viewport').getAttribute('style')).toBe(viewport);
 expect(await page.locator('.react-flow__edge').first().evaluate(e=>getComputedStyle(e).animationName)).toBe('story-edge-arrive');
 expect(await page.locator('.entity-node.recently-changed').first().evaluate(e=>getComputedStyle(e).animationDuration)).toBe('0.38s');
 await page.screenshot({path:info.outputPath('growing-graph.png'),animations:'disabled'});
});

// Controlled event-contract test, NOT evidence of real microphone transcription.
test('controlled speech lifecycle: direct send finalizes once, stop and cancel never send',async({page})=>{
 await page.addInitScript(()=>{
  window.__stops=0;
  navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[{stop(){window.__stops++;}}]});
  window.AudioContext=class{state='running';resume(){return Promise.resolve();}close(){return Promise.resolve();}createMediaStreamSource(){return {connect(){}};}createAnalyser(){return {fftSize:256,frequencyBinCount:128,getByteFrequencyData(v){v.fill(0);}};}};
  window.SpeechRecognition=class{
   start(){window.__recognizer=this;queueMicrotask(()=>this.onstart());}
   stop(){window.__stopRequested=true;}
   abort(){this.onend?.();}
  };
 });
 let sends=0;page.on('request',r=>{if(r.url().endsWith('/api/chat')&&r.method()==='POST')sends++;});
 await page.goto('/');await page.getByRole('button',{name:'Start microphone'}).click();
 await expect(page.getByRole('button',{name:'Send recording'})).toBeEnabled();
 await page.getByRole('button',{name:'Send recording'}).click();expect(sends).toBe(0);
 await page.evaluate(()=>{const result=[{transcript:"My parents and sister are coming for dad's post-surgery care."}];result.isFinal=true;window.__recognizer.onresult({resultIndex:0,results:[result]});window.__recognizer.onend();window.__recognizer.onend();});
 await expect(page.locator('.message.user')).toHaveCount(1);await expect(page.locator('.message.assistant')).toHaveCount(1);expect(sends).toBe(1);
 await page.getByRole('button',{name:'Start microphone'}).click();await expect(page.getByRole('button',{name:'Stop recording'})).toBeEnabled();await page.getByRole('button',{name:'Stop recording'}).click();
 await page.evaluate(()=>{const r=[{transcript:'A draft for review'}];r.isFinal=true;window.__recognizer.onresult({resultIndex:0,results:[r]});window.__recognizer.onend();});
 await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('A draft for review');expect(sends).toBe(1);
 await page.getByRole('button',{name:'Start microphone'}).click();await expect(page.getByRole('button',{name:'Stop recording'})).toBeEnabled();await page.getByRole('button',{name:'Cancel recording'}).click();await expect(page.getByRole('textbox',{name:'Message',exact:true})).toHaveValue('A draft for review');expect(sends).toBe(1);
 expect(await page.evaluate(()=>window.__stops)).toBeGreaterThanOrEqual(3);
 await page.getByRole('textbox',{name:'Message',exact:true}).fill('');await page.getByRole('button',{name:'Start microphone'}).click();await expect(page.getByRole('button',{name:'Send recording'})).toBeEnabled();await page.getByRole('button',{name:'Send recording'}).click();await page.evaluate(()=>window.__recognizer.onend());await expect(page.getByRole('alert')).toContainText('No finalized speech');expect(sends).toBe(1);
});
