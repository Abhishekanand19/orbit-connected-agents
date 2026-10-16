import {test,expect} from '@playwright/test';
test('simulated inputs, truthful receipts, actual graph views and new conversation',async({page,request},testInfo)=>{
 await page.goto('/');const demo=page.getByRole('region',{name:'Isolated family demo'});await expect(demo).toBeVisible();
 for(const key of ['rumor','roads','pending','confirmed','available']){
  await demo.getByLabel('Demo incoming event').selectOption(key);
  await demo.getByRole('button',{name:'Introduce input',exact:true}).click();
  await expect(demo.getByRole('button',{name:'Introduce input',exact:true})).toBeDisabled();
  await expect(demo.getByRole('button',{name:'Ask existing specialists'})).toBeEnabled();
 }
 await demo.getByRole('button',{name:'Why?',exact:true}).click();
 const why=page.getByRole('dialog',{name:'Why did Orbit do this?'});await expect(why).toContainText('PROPOSED');await expect(why).toContainText('Internal demo cab arrangement');
 await page.screenshot({path:testInfo.outputPath('family-receipt.png'),fullPage:true});
 await why.getByRole('button',{name:'Close explanation'}).click();
 for(const mode of ['Graph','Simple']){
  await page.getByRole('button',{name:'Open '+mode+' View',exact:true}).click();
  await expect(page.getByTestId('graph-canvas')).toBeVisible();
  await expect(page.locator('[data-entity-id="family:appointment"]')).toBeVisible();
  await expect(page.locator('[data-entity-id="family:cab"]')).toBeVisible();
  await page.getByRole('button',{name:'Close graph workspace'}).click();
 }
 await demo.getByLabel('Demo incoming event').selectOption('video');await demo.getByRole('button',{name:'Introduce input',exact:true}).click();
 await expect.poll(async()=>{const state=await (await request.get('http://127.0.0.1:8002/api/demo')).json();return state.received.find(e=>e.event==='video')?.conversation_id;}).toBe('family:session:2');
 await expect(page.locator('.message-bubble')).toHaveCount(1);
 await expect(page.locator('.message-bubble')).toContainText('The hospital confirms the follow-up can happen by video');
});
