import {test,expect} from '@playwright/test';
const names=['Gmail','Google Drive','Google Calendar','Google Tasks','Slack','Microsoft Excel','Microsoft Teams'];
const welcome=page=>expect(page.getByRole('heading',{name:'Sign in — Orbit demo'})).toBeVisible();

test('exact reference, private editable input, seven preview switches and three navigation cycles',async({page},info)=>{
 const requests=[];page.on('request',r=>requests.push({url:r.url(),body:r.postData()||''}));
 for(let round=0;round<3;round++){
  await page.goto('/welcome');if(round===1)await page.reload();await welcome(page);
  await expect(page.locator('.signin-reference>img')).toHaveAttribute('src','/brand/signin-reference.png');
  const input=page.getByRole('textbox',{name:'Email or phone'});await input.fill('private-demo@example.test');await input.press('Backspace');await expect(input).toHaveValue('private-demo@example.tes');await input.fill('private-demo@example.test');
  if(!round)await page.screenshot({path:info.outputPath('signin-reference.png')});
  await page.getByRole('button',{name:'Next',exact:true}).click();await expect(page.getByRole('switch')).toHaveCount(7);
  for(const name of names){const control=page.getByRole('switch',{name:`${name} preview connection`});await expect(control).not.toBeChecked();await control.click();await expect(control).toBeChecked();await expect.poll(()=>control.evaluate(e=>getComputedStyle(e).backgroundColor)).toBe('rgb(41, 131, 83)');await control.click();await expect(control).not.toBeChecked();await control.click();}
  await expect(page.getByText(/Preview controls only/)).toBeVisible();await expect(page.getByText('Unavailable',{exact:true})).toHaveCount(0);
  if(!round)await page.screenshot({fullPage:true,path:info.outputPath('preview-connections.png'),animations:'disabled'});
  await page.getByRole('button',{name:'Continue to Orbit'}).click();await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();await expect(page.getByRole('alert')).toHaveCount(0);
 }
 expect(requests.filter(r=>/\/auth\/|onboarding\/connections|disconnect/.test(r.url))).toEqual([]);
 expect(requests.some(r=>r.url.includes('private-demo')||r.body.includes('private-demo'))).toBe(false);
 await expect(page.locator('.sidebar-bottom')).toContainText('Plus subscription');
 for(const [name,subtitle] of [['Coordinator','Manages all agents'],['Planner','Plans actions & keeps notes'],['Researcher','Finds information'],['Communication Assistant','Handles messages & replies'],['Task Manager','Creates & tracks tasks']]){await page.getByRole('navigation',{name:'Your bots'}).getByRole('button',{name,exact:true}).click();await expect(page.locator('.header-name')).toContainText(subtitle);}
 await page.getByRole('navigation',{name:'Your bots'}).getByRole('button',{name:'Coordinator',exact:true}).click();await page.screenshot({path:info.outputPath('workspace-header.png')});
});

test('workspace creation recovers without reload after a genuine network failure',async({page})=>{
 let tries=0;await page.route('**/api/story/workspaces',async r=>{tries++;if(tries===1)await r.abort('connectionrefused');else await r.continue();});
 await page.goto('/welcome');await page.getByRole('button',{name:'Next',exact:true}).click();await page.getByRole('button',{name:'Continue to Orbit'}).click();
 await expect(page.getByRole('alert')).toContainText('Cannot reach the Orbit API');
 await page.getByRole('button',{name:'Retry connection'}).click();await expect(page.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();expect(tries).toBe(2);
 expect(await page.evaluate(()=>localStorage.getItem('orbit.onboarding.complete.v1'))).toBe('true');
});

test('mobile reference and preview controls remain editable without horizontal overflow',async({page},info)=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/welcome');await welcome(page);await page.getByRole('textbox',{name:'Email or phone'}).fill('Demo');await page.screenshot({path:info.outputPath('signin-mobile.png')});
 await page.getByRole('button',{name:'Next',exact:true}).click();await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.getByRole('switch',{name:'Microsoft Teams preview connection'}).click();await expect(page.getByRole('switch',{name:'Microsoft Teams preview connection'})).toBeChecked();
});

test('original dedicated onboarding tab still opens',async({page,context})=>{
 await page.goto('/');const opened=context.waitForEvent('page');await page.getByRole('button',{name:'Get started in a new tab'}).click();const tab=await opened;await welcome(tab);await tab.getByRole('button',{name:'Next',exact:true}).click();await tab.getByRole('button',{name:'Continue to Orbit'}).click();await expect(tab.getByRole('heading',{name:'Coordinator',exact:true})).toBeVisible();
});
