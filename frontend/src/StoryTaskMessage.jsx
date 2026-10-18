import React,{useEffect,useState} from 'react';
import {actionRequest} from './services';
import StreamingText from './StreamingText';
import StoryChecklist from './StoryChecklist';

export default function StoryTaskMessage({content,actionIds=[],checklist=[],streamId,onComplete}){
 const [email,setEmail]=useState(null),[ready,setReady]=useState(false);
 useEffect(()=>{
  if(!actionIds.length)return;
  let active=true;
  const load=()=>actionRequest('/api/actions').then(r=>{if(active)setEmail(r.actions.find(a=>actionIds.includes(a.id)&&a.application==='gmail')||null);}).catch(()=>{if(active)setEmail(null);});
  load();window.addEventListener('orbit:graph-changed',load);
  return()=>{active=false;window.removeEventListener('orbit:graph-changed',load);};
 },[actionIds]);
 if(checklist.length)return <><p><StreamingText id={streamId+':intro'} text="I've made a short to-do list for you." onComplete={()=>setReady(true)}/></p>{ready&&<><StoryChecklist tasks={checklist}/><p><StreamingText id={streamId+':outro'} text="I'll keep these tasks linked to the updated plan." onComplete={onComplete}/></p></>}</>;
 let text=content;
 if(email){
  const status=email.status==='VERIFIED'?'[✅] Email sent to Priya. Verified submission: '+email.payload.to.join(', ')+'.':
   email.status==='UNKNOWN'?'[⏳] Email submission is unverified. Do not resend.':
   email.status==='FAILED'?'[❌] Email failed. Review the action result.':
   email.status==='EXECUTING'?'[⏳] Email is executing; provider readback is pending.':
   email.status==='REJECTED'?'[⏳] Email proposal rejected. Nothing sent.':
   email.status==='APPROVED'?'[⏳] Email approved; execution and readback pending.':'📧 Waiting for approval to email Priya.';
  text=text.replace('📧 Waiting for approval to email Priya.',status);
 }
 return <p><StreamingText id={streamId} text={text} onComplete={onComplete}/></p>;
}
