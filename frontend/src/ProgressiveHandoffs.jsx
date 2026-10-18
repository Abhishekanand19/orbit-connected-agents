import React,{useState} from 'react';
import Avatar from './Avatar';
import StoryTaskMessage from './StoryTaskMessage';
import StreamingText from './StreamingText';
import RoutePreview from './RoutePreview';
import ApprovalPanel from './ApprovalPanel';
import {defaults,displayName} from './services';
// Presentation only: completion gates the next speaker and approval controls.
export default function ProgressiveHandoffs({story,bots,ready=true,messageId}){
 const handoffs=story.handoffs||[],[completed,setCompleted]=useState(0);
 const identity=h=>bots.find(b=>b.id===h.agent)||defaults.find(b=>b.id===h.agent);
 if(!ready)return null;
 return <>
 {handoffs.slice(0,completed+1).map((h,i)=><div className="inline-handoff" key={h.run_id||i}>
  <Avatar {...identity(h)} size={28}/><div>
   {!story.direct_specialist&&<small className="handoff-label">{i?displayName(handoffs[i-1].name):'Coordinator'} → {displayName(h.name)}</small>}
   <strong className="bot-identity" style={{color:identity(h)?.color}}>@ {displayName(h.name)}</strong>
   {h.agent==='tasks'?<StoryTaskMessage content={h.content} actionIds={story.action_ids} checklist={story.checklist} streamId={messageId+':'+i} onComplete={()=>setCompleted(n=>Math.max(n,i+1))}/>:<p className={h.agent==='research'?'research-citations':undefined}><StreamingText id={messageId+':'+i} text={h.content} onComplete={()=>setCompleted(n=>Math.max(n,i+1))}/></p>}
   {i<completed&&h.agent==='tasks'&&story.route_preview&&<RoutePreview/>}
  </div>
 </div>)}
 {completed<handoffs.length&&<div className="specialist-typing" role="status"><span>{displayName(handoffs[completed].name)}<span className="activity-dots"><i/><i/><i/></span></span></div>}
 {completed===handoffs.length&&story.action_ids?.length>0&&<ApprovalPanel inline actionIds={story.action_ids}/>}
 </>;
}
