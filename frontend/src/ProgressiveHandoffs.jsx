import React,{useEffect,useState} from 'react';
import Avatar from './Avatar';
import StoryTaskMessage from './StoryTaskMessage';
import RoutePreview from './RoutePreview';
import ApprovalPanel from './ApprovalPanel';
import {defaults,displayName} from './services';
function SourcedText({text}){return <p className="research-citations">{text.split(/(https:\/\/[^\s]+)/g).map((part,i)=>part.startsWith('https://')?<a key={i} href={part} target="_blank" rel="noopener noreferrer">{part}</a>:part)}</p>;}

// Presentation only: every finding and graph change has already been persisted.
export default function ProgressiveHandoffs({story,bots}){
 const handoffs=story.handoffs||[];
 const [visible,setVisible]=useState(0);
 useEffect(()=>{
  setVisible(0);
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){setVisible(handoffs.length);return;}
  const timers=handoffs.map((_,i)=>setTimeout(()=>setVisible(i+1),450+i*650));
  return()=>timers.forEach(clearTimeout);
 },[story]);
 const identity=h=>bots.find(b=>b.id===h.agent)||defaults.find(b=>b.id===h.agent);
 return <>
  {handoffs.slice(0,visible).map((h,i)=><div className="inline-handoff" key={h.run_id||i}>
   <Avatar {...identity(h)} size={28}/><div>
    {!story.direct_specialist&&<small className="handoff-label">{i?displayName(handoffs[i-1].name):'Coordinator'} → {displayName(h.name)}</small>}
    <strong className="bot-identity" style={{color:identity(h)?.color}}>@ {displayName(h.name)}</strong>
    {h.agent==='tasks'?<StoryTaskMessage content={h.content} actionIds={story.action_ids} checklist={story.checklist}/>:h.agent==='research'?<SourcedText text={h.content}/>:<p>{h.content}</p>}
    {h.agent==='tasks'&&story.route_preview&&<RoutePreview/>}
   </div>
  </div>)}
  {visible<handoffs.length&&<div className="specialist-typing" role="status" aria-label={`${displayName(handoffs[visible].name)} response appearing`}><Avatar {...identity(handoffs[visible])} size={28}/><span>{displayName(handoffs[visible].name)}<span className="activity-dots"><i/><i/><i/></span></span></div>}
  {visible===handoffs.length&&story.action_ids?.length>0&&<ApprovalPanel inline actionIds={story.action_ids}/>}
 </>;
}
