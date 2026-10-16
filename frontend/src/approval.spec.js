import {test,expect} from '@playwright/test';

test('review exact payload, approve and verify one task, reject another, survive reload',async({page,request},testInfo)=>{
 await page.goto('/');
 const panel=page.getByRole('region',{name:'Action approvals'});
 await expect(panel).toBeVisible();
 const approve=panel.locator('.approval-card').filter({hasText:'approve-task'});
 const reject=panel.locator('.approval-card').filter({hasText:'reject-task'});
 await expect(approve).toContainText('Prepare the launch notes');
 await expect(approve.locator('pre')).toContainText('"status": "DONE"');
 let before=await request.get('http://127.0.0.1:8002/api/nodes/approve-task');
 expect((await before.json()).properties.status).toBe('OPEN');
 await page.screenshot({path:testInfo.outputPath('approval-desktop.png'),fullPage:true});
 await approve.getByRole('button',{name:'Approve exact action'}).click();
 await expect(approve.locator('summary')).toContainText('VERIFIED');
 await reject.getByRole('button',{name:'Reject',exact:true}).click();
 await expect(reject.locator('summary')).toContainText('REJECTED');
 expect((await (await request.get('http://127.0.0.1:8002/api/nodes/approve-task')).json()).properties.status).toBe('DONE');
 expect((await (await request.get('http://127.0.0.1:8002/api/nodes/reject-task')).json()).properties.status).toBe('OPEN');
 await page.reload();await expect(panel).toBeVisible();await expect(approve.locator('summary')).toContainText('VERIFIED');
 await page.setViewportSize({width:390,height:844});
 await page.getByRole('button',{name:'Close settings',exact:true}).click();
 await expect(panel).toBeVisible();
 await page.screenshot({path:testInfo.outputPath('approval-mobile.png'),fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});
