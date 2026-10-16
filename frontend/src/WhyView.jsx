import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {X,RefreshCw,GitFork} from 'lucide-react';
import {actionRequest} from './services';
import './why.css';
import {relationLabel} from './graph/models';

const relation={DEPENDS_ON:'depends on',AFFECTS:'affects',ASSIGNED_TO:'is assigned to',AVAILABLE_FOR:'is available for',RELATED_TO:'is connected to',SUPPORTED_BY:'is supported by',VERIFIED_BY:'was verified by'};
const nodeName=n=>n.properties.name||n.properties.text||n.properties.summary||n.properties.content||n.id;
export function WhyButton({id}){
 const [open,setOpen]=useState(false);
 return <><button type="button" className="why-button" onClick={e=>{e.preventDefault();e.stopPropagation();setOpen(true);}}>Why?</button>{open&&createPortal(<WhyView id={id} close={()=>setOpen(false)}/>,document.body)}</>;
}
export default function WhyView({id,close}){
 const dialog=useRef(null),sequence=useRef(0);
 const [current,setCurrent]=useState(id),[receipt,setReceipt]=useState(null),[error,setError]=useState('');
 async function refresh(){
  const version=++sequence.current;setError('');setReceipt(null);
  try{const data=await actionRequest('/api/receipts/'+encodeURIComponent(current));if(version===sequence.current)setReceipt(data);}
  catch(e){if(version===sequence.current)setError(e.message);}
 }
 useEffect(()=>{const prior=document.activeElement;dialog.current.showModal();return()=>prior?.focus();},[]);
 useEffect(()=>{refresh();window.addEventListener('orbit:graph-changed',refresh);return()=>{sequence.current++;window.removeEventListener('orbit:graph-changed',refresh);};},[current]);
 const names=Object.fromEntries((receipt?.graph.nodes||[]).map(n=>[n.id,nodeName(n)]));
 return <dialog ref={dialog} className="why-dialog" aria-label="Why did Orbit do this?" onCancel={e=>{e.preventDefault();close();}} onClick={e=>e.stopPropagation()}>
  <header><div><GitFork size={20}/><h2>Why did Orbit do this?</h2></div><button className="icon-button" aria-label="Refresh receipt" onClick={refresh}><RefreshCw size={17}/></button><button className="icon-button" aria-label="Close explanation" onClick={close}><X size={20}/></button></header>
  {error?<p role="alert">{error}</p>:!receipt?<p role="status">Reading saved evidence…</p>:<>
   <div className="why-heading"><span className={'approval-status status-'+receipt.status.toLowerCase()}>{receipt.status}</span><small>{receipt.evidence_basis}</small></div>
   <ol className="why-flow">
    <li><span>What started this</span><p>{receipt.trigger||'No triggering event was recorded.'}</p></li>
    {!!receipt.paths.length&&<li><span>Connected consequences</span>{receipt.paths.map((path,i)=><div className="why-path" key={i}><p>{path.labels.join(' → ')}</p>{path.segments.map(s=><small key={s.edge.id}>{names[s.edge.source]||s.edge.source} {relation[s.edge.type]||relationLabel(s.edge.type)} {names[s.edge.target]||s.edge.target}<br/></small>)}<small>Evidence: {path.evidence_status.toLowerCase()}{!path.complete?' · Some relationship records are unavailable':''}</small></div>)}</li>}
    {!!receipt.alternatives.length&&<li><span>People and conflicts</span>{receipt.alternatives.map(a=><div className="why-path" key={a.entity_id}><p>{names[a.entity_id]||a.entity_id} � {{ACT:'Possible alternative',WAIT:'Needs confirmation',CONFLICT:'Unavailable',NO_CHANGE:'Keep current assignment'}[a.state]}</p><small>{a.reason}{a.constraint_ids.length?' Conflicts: '+a.constraint_ids.map(id=>names[id]||id).join(', '):''}</small></div>)}</li>}
    {!!receipt.previous.length&&<li><span>Earlier memory used</span>{receipt.previous.map(p=><div key={p.id}><button className="why-link" onClick={()=>setCurrent(p.id)}>{p.title}</button><small>{p.retrieval?'Retrieved for this analysis from saved memory.':'Linked as supporting evidence; retrieval was not recorded.'}</small></div>)}</li>}
    <li><span>Decision</span><p>{receipt.reason}</p>{receipt.agents.length>0&&<small>Involved: {[...new Set(receipt.agents.map(a=>a.name))].join(', ')}</small>}</li>
    {receipt.tool&&<li><span>Action and outcome</span><p>{receipt.status==='VERIFIED'?'The approved action was completed and matched a fresh readback.':receipt.status==='UNKNOWN'?'The outcome is unconfirmed. Do not assume completion.':receipt.status==='FAILED'?'The action failed.':receipt.status==='REJECTED'?'You rejected this action.':receipt.status==='EXECUTING'?'Execution is in progress; completion is not confirmed.':receipt.status==='APPROVED'?'Approved; completion is not confirmed.':'Awaiting your review. No completion is recorded.'}</p><small>{receipt.approval?'Approval recorded.':'No approval recorded.'} {receipt.verification.verified?'Readback matched.':'No successful readback recorded.'}</small></li>}
   </ol>
   <details className="why-technical"><summary>Inspect technical evidence</summary><p>Saved IDs, relationship directions, provenance, approval history and execution results.</p><pre>{JSON.stringify(receipt,null,2)}</pre></details>
  </>}
 </dialog>;
}
export function DecisionReceipts(){
 const [items,setItems]=useState([]),[error,setError]=useState('');
 useEffect(()=>{let active=true;const load=()=>actionRequest('/api/receipts').then(d=>{if(active){setItems(d.receipts);setError('');}}).catch(e=>{if(active)setError(e.message);});load();window.addEventListener('orbit:graph-changed',load);return()=>{active=false;window.removeEventListener('orbit:graph-changed',load);};},[]);
 if(!items.length&&!error)return null;
 return <section className="decision-receipts" aria-label="Decision receipts"><h3>Decisions & evidence</h3>{error&&<p role="alert">{error}</p>}{items.map(item=><div className="decision-row" key={item.id}><span>{item.title}</span><small>{item.status}</small><WhyButton id={item.id}/></div>)}</section>;
}
