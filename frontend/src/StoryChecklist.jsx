import React,{useEffect,useState} from 'react';
import {chatRequest} from './services';
export default function StoryChecklist({tasks}){
 const [items,setItems]=useState(tasks),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{if(!tasks.length)return;let active=true;chatRequest('/api/story/checklist').then(r=>{if(active)setItems(r.tasks);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[tasks]);
 if(!items.length)return null;
 async function toggle(item){setBusy(true);setError('');try{const r=await chatRequest('/api/story/checklist/'+item.id.split(':').at(-1),{checked:!item.checked});setItems(r.tasks);window.dispatchEvent(new Event('orbit:graph-changed'));}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div className="story-checklist" aria-label="Plan checklist">{items.map(item=><label key={item.id}><input type="checkbox" checked={item.checked} disabled={busy} onChange={()=>toggle(item)}/><span>{item.label}{item.checked&&<small> User-reported complete; no external verification implied.</small>}</span></label>)}{error&&<p role="alert">{error}</p>}</div>;
}
