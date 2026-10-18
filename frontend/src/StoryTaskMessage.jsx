import React,{useEffect,useState} from 'react';
import {actionRequest} from './services';
import StoryChecklist from './StoryChecklist';

export default function StoryTaskMessage({content,actionIds=[],checklist=[]}){
 const [email,setEmail]=useState(null);
 useEffect(()=>{
  if(!actionIds.length)return;
  let active=true;
  const load=()=>actionRequest('/api/actions').then(r=>{if(active)setEmail(r.actions.find(a=>actionIds.includes(a.id)&&a.application==='gmail')||null);}).catch(()=>{if(active)setEmail(null);});
  load();window.addEventListener('orbit:graph-changed',load);
  return()=>{active=false;window.removeEventListener('orbit:graph-changed',load);};
 },[actionIds]);
 if(checklist.length)return <><p>I've made a short to-do list for you.</p><StoryChecklist tasks={checklist}/><p>I'll keep these tasks linked to the updated plan.</p></>;
 let text=content;
 if(email){
  const status=email.status==='VERIFIED'?'[✓] Email sent to Priya. Verified submission: '+email.payload.to.join(', ')+'.':
   email.status==='UNKNOWN'?'[ ] Email submission is unverified. Do not resend.':
   email.status==='FAILED'?'[✗] Email failed. Review the action result.':
   email.status==='EXECUTING'?'[ ] Email is executing; provider readback is pending.':
   email.status==='REJECTED'?'[ ] Email proposal rejected. Nothing sent.':
   email.status==='APPROVED'?'[ ] Email approved; execution and readback pending.':'[ ] Email to Priya awaiting approval.';
  text=text.replace('[ ] Email to Priya awaiting approval.',status);
 }
 return <p>{text}</p>;
}
