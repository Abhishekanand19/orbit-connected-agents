import React,{useEffect,useState} from 'react';
import {ShieldCheck,Check,X,RefreshCw} from 'lucide-react';
import {actionRequest} from './services';
import './approvals.css';

const names={calendar:'Google Calendar',gmail:'Gmail',slack:'Slack',task:'Orbit Task Manager'};
const terminal=new Set(['VERIFIED','REJECTED','SUPERSEDED']);
export default function ApprovalPanel(){
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
 if(!actions.length&&!error)return null;
 return <section className="approval-panel" aria-label="Action approvals">
  <header><div><ShieldCheck size={18}/><strong>Your approval, then action</strong></div><button type="button" className="icon-button" aria-label="Refresh approvals" onClick={refresh}><RefreshCw size={15}/></button></header>
  <p className="approval-intro">Review the exact changes. Each approval applies to this action only.</p>
  {error&&<p role="alert" className="approval-error">{error}</p>}
  {actions.map(action=><details className="approval-card" key={action.id} open={!terminal.has(action.status)}>
   <summary><span>{names[action.application]||action.application}</span><span className={`approval-status status-${action.status.toLowerCase()}`}>{action.status.replaceAll('_',' ')}</span></summary>
   <p>{action.reason}</p><p className="approval-affected">Affects: {action.affected_ids.map(id=>`${action.affected_labels?.[id]||id} (${id})`).join(', ')}</p>
   <div className="approval-exact"><strong>Exact proposed changes</strong><pre>{JSON.stringify(action.payload,null,2)}</pre></div>
   {action.application==='calendar'&&<p className="approval-affected">Calendar attendee changes can notify guests. Notification setting: {action.payload.send_updates}.</p>}
   {action.error&&<p className="approval-error">{action.error}</p>}
   {action.status==='VERIFIED'&&<p className="approval-verified"><Check size={14}/> Verified by fresh readback · {action.verification.provider_id}</p>}
   {['AWAITING_APPROVAL','APPROVED'].includes(action.status)&&<div className="approval-buttons"><button type="button" className="primary" disabled={!!busy} onClick={()=>decide(action,'approve')}><Check size={15}/>{busy===action.id?'Checking…':'Approve exact action'}</button><button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'reject')}><X size={15}/>Reject</button></div>}
   {action.status==='UNKNOWN'&&<button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'verify')}>Check readback — do not resend</button>}
   {action.status==='FAILED'&&action.retryable&&<button type="button" className="secondary" disabled={!!busy} onClick={()=>decide(action,'retry')}>Retry the approved action safely</button>}
   {['AWAITING_APPROVAL','FAILED'].includes(action.status)&&<button type="button" className="text-button" disabled={!!busy} onClick={()=>decide(action,'refresh')}>Refresh proposal for a new review</button>}
   <small className="approval-affected">{action.tool} · {action.id}</small>
  </details>)}
 </section>;
}
