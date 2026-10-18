import ResponsePause from './ResponsePause';
import React,{useState} from 'react';
import Avatar from './Avatar';
import StoryTaskMessage from './StoryTaskMessage';
import StreamingText from './StreamingText';
import RoutePreview from './RoutePreview';
import ApprovalPanel from './ApprovalPanel';
import {defaults,displayName} from './services';
// Presentation only: completion gates the next speaker and approval controls.
export default function ProgressiveHandoffs(props){return props.ready===false?null:<Handoffs {...props}/>;}
function Handoffs({story,bots,ready=true,messageId}){
 const handoffs=story.handoffs||[],[completed,setCompleted]=useState(0);
 const [transitionAt,setTransitionAt]=useState(()=>Date.now()+1300);
 const finish=i=>{setTransitionAt(Date.now()+1300);setCompleted(n=>Math.max(n,i+1));};
 const identity=h=>bots.find(b=>b.id===h.agent)||defaults.find(b=>b.id===h.agent);
 if(!ready)return null;
 return <>
 {handoffs.slice(0,completed+1).map((h,i)=><div className="inline-handoff" key={h.run_id||i}>
  <Avatar {...identity(h)} size={28}/><div>
   {!story.direct_specialist&&<small className="handoff-label">{i?displayName(handoffs[i-1].name):'Coordinator'} → {displayName(h.name)}</small>}
   <strong className="bot-identity" style={{color:identity(h)?.color}}>@ {displayName(h.name)}</strong>
   <ResponsePause id={messageId+':pause:'+i} until={i<completed?0:transitionAt}>{h.agent==='tasks'?<StoryTaskMessage content={h.content} actionIds={story.action_ids} checklist={story.checklist} streamId={messageId+':'+i} onComplete={()=>finish(i)}/>:<p className={h.agent==='research'?'research-citations':undefined}><StreamingText id={messageId+':'+i} text={h.content} onComplete={()=>finish(i)}/></p>}</ResponsePause>
   {i<completed&&h.agent==='tasks'&&story.route_preview&&<RoutePreview/>}
  </div>
 </div>)}
 {completed<handoffs.length&&<span className="specialist-typing sr-only">Response presentation</span>}
 {completed===handoffs.length&&story.action_ids?.length>0&&<ApprovalPanel inline actionIds={story.action_ids}/>}
 </>;
}
