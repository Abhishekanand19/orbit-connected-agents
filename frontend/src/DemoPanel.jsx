import React,{useEffect,useState} from 'react';
import {chatRequest} from './services';
import {WhyButton} from './WhyView';
export default function DemoPanel(){
 const [state,setState]=useState(null),[selected,setSelected]=useState('rumor'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState(null);
 useEffect(()=>{chatRequest('/api/demo').then(setState).catch(()=>{});},[]);
 if(!state?.enabled)return null;
 const received=state.received.find(r=>r.event===selected);
 async function run(analyze){
  setBusy(true);setError('');setResult(null);
  try{
   const data=await chatRequest('/api/demo/'+selected+(analyze?'/analyze':''),{});
   if(analyze)setResult(data);
   setState(await chatRequest('/api/demo'));
   window.dispatchEvent(new Event('orbit:graph-changed'));
   window.dispatchEvent(new Event('orbit:demo-session'));
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 return <section className="decision-receipts" aria-label="Isolated family demo"><h3>Family & work · isolated demo</h3><p style={{fontSize:12}}>Simulated incoming messages and internal cab records. External writes require separate exact approval and verified readback.</p>
 <select aria-label="Demo incoming event" value={selected} disabled={busy} onChange={e=>{setSelected(e.target.value);setResult(null);}}>{state.events.map(e=><option key={e.id} value={e.id}>Session {e.session} · {e.id} · {e.status}</option>)}</select>
 <p style={{fontSize:13}}>{state.events.find(e=>e.id===selected)?.text}</p>
 <div className="approval-buttons"><button className="secondary" disabled={busy||!!received} onClick={()=>run(false)}>Introduce input</button><button className="primary" disabled={busy||!received} onClick={()=>run(true)}>{busy?'Working…':'Ask existing specialists'}</button>{received&&<WhyButton id={received.decision_id}/>}</div>
 <small>Specialist analysis uses your configured model. Review proposals in the approval panel.</small>
 {error&&<p role="alert">{error}</p>}{result&&<div aria-label="Demo agent activity">{result.activity.map(r=><p key={r.id}>{r.properties.owner}: {r.properties.status}{r.properties.error?' · '+r.properties.error:''}</p>)}{result.proposal_errors?.map((e,i)=><p role="alert" key={i}>{e}</p>)}</div>}
 </section>;
}
