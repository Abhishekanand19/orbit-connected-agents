import React,{useEffect,useState} from 'react';
import {ShieldCheck,Check,X,RefreshCw} from 'lucide-react';
import {actionRequest} from './services';
import './approvals.css';
import {WhyButton} from './WhyView';

const names={calendar:'Google Calendar',gmail:'Gmail',slack:'Slack',task:'Orbit Task Manager'};
const statusLabel={AWAITING_APPROVAL:'Awaiting your approval',APPROVED:'Approved',EXECUTING:'In progress',VERIFIED:'Verified',FAILED:'Failed',UNKNOWN:'Not yet verified',REJECTED:'Rejected',SUPERSEDED:'Replaced'};
const fieldLabel=key=>({task_id:'Target task',assignee_id:'Assigned to',changes:'Changes',starts_at:'Start time',ends_at:'End time',status:'Status'}[key]||key.replaceAll('_',' '));
const exactValue=(key,value,action)=>{
 if(['starts_at','ends_at'].includes(key)&&typeof value==='string'&&!Number.isNaN(Date.parse(value)))return new Date(value).toLocaleString('en-IN',{day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'})+' IST';
 if(['task_id','assignee_id'].includes(key))return action.affected_labels?.[value]||String(value);
 return String(value);
};
const terminal=new Set(['VERIFIED','REJECTED','SUPERSEDED']);
export default function ApprovalPanel({actionIds,messageId,inline=false}){
 const [actions,setActions]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState('');
 async function refresh(){
  try{const data=await actionRequest('/api/actions');setActions(data.actions);setError('');}
  catch(e){setError(e.message);}
 }
 useEffect(()=>{
  let active=true;
  actionRequest('/api/actions/session',{}).then(()=>{if(active)refresh();}).catch(e=>{if(active)setError(e.message);});
  const changed=()=>refresh();window.addEventListener('orbit:graph-changed',changed);
  return()=>{active=false;window.removeEventListener('orbit:graph-changed',changed);};
 },[]);
 async function decide(action,verb){
  if(busy)return;setBusy(action.id);setError('');
  try{await actionRequest(`/api/actions/${encodeURIComponent(action.id)}/${verb}`,{digest:action.digest});await refresh();window.dispatchEvent(new Event('orbit:graph-changed'));}
  catch(e){await refresh();setError(e.message);}
  finally{setBusy('');}
 }
 const shown=actionIds?actions.filter(a=>actionIds.includes(a.id)):messageId?actions.filter(a=>a.message_id===messageId):actions;
 if(!shown.length&&!error)return null;
 return <section className={`approval-panel ${inline?'inline-approval':''}`} aria-label="Action approvals">
  {!inline&&<><header><div><ShieldCheck size={18}/><strong>Your approval, then action</strong></div><button type="button" className="icon-button" aria-label="Refresh approvals" onClick={refresh}><RefreshCw size={15}/></button></header>
  <p className="approval-intro">Review the exact changes. Each approval applies to this action only.</p></>}
  {error&&<p role="alert" className="approval-error">{error}</p>}
  {shown.map(action=><details className="approval-card" key={action.id} open={!terminal.has(action.status)}>
   <summary><span>{names[action.application]||action.application}</span><span className={`approval-status status-${action.status.toLowerCase()}`}>{statusLabel[action.status]||action.status.replaceAll('_',' ')}</span>{<WhyButton id={action.id}/>}</summary>
   <p>{inline&&action.application==='task'?'Review this internal task change. It does not alter a third-party booking.':action.reason}</p><p className="approval-affected">Affects: {action.affected_ids.map(id=>action.affected_labels?.[id]||id).join(', ')}</p>
   {inline?<div className="approval-readable"><strong>Exact proposed changes</strong><dl>{Object.entries(action.payload).map(([key,value])=><div key={key}><dt>{fieldLabel(key)}</dt><dd>{typeof value==='object'&&value!==null?Object.entries(value).map(([field,change])=><div key={field}><span>{fieldLabel(field)}</span>: <strong>{exactValue(field,change,action)}</strong></div>):exactValue(key,value,action)}</dd></div>)}</dl><details><summary>Inspect exact payload and evidence</summary><p>{action.reason}</p><pre>{JSON.stringify(action.payload,null,2)}</pre><small>{action.tool} · {action.id}</small></details></div>:<div className="approval-exact"><strong>Exact proposed changes</strong><pre>{JSON.stringify(action.payload,null,2)}</pre></div>}
   {action.application==='calendar'&&<p className="approval-affected">Calendar attendee changes can notify guests. Notification setting: {action.payload.send_updates}.</p>}
   {action.error&&<p className="approval-error">{action.error}</p>}
   {action.status==='VERIFIED'&&<p className="approval-verified"><Check size={14}/> Verified by fresh readback · {action.verification.provider_id}</p>}
   {['AWAITING_APPROVAL','APPROVED'].includes(action.status)&&<div className="approval-buttons"><button type="button" className="primary" disabled={!!busy} onClick={()=>decide(action,'approve')}><Check size={15}/>{busy===action.id?'Checking…':'Approve exact action'}</button><button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'reject')}><X size={15}/>Reject</button></div>}
   {action.status==='UNKNOWN'&&<button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'verify')}>Check readback — do not resend</button>}
   {action.status==='FAILED'&&action.retryable&&<button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'retry')}>Retry the approved action safely</button>}
   {['AWAITING_APPROVAL','FAILED'].includes(action.status)&&<button type="button" className="text-button" disabled={!!busy} onClick={()=>decide(action,'refresh')}>Refresh proposal for a new review</button>}
   {!inline&&<small className="approval-affected">{action.tool} · {action.id}</small>}
  </details>)}
 </section>;
}
