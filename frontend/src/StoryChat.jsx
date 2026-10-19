import React,{useState,useEffect} from 'react';
import {chatRequest,STORY_KEY} from './services';
import './story.css';

let initialization;
function initialize(){
 if(!initialization)initialization=(async()=>{
  const publicDemo=import.meta.env.VITE_ORBIT_PUBLIC_DEMO==='true';
  if(publicDemo)localStorage.setItem('orbit.chat.mode','deterministic');
  if(localStorage.getItem('orbit.chat.mode')!=='normal'){
   if(publicDemo&&(sessionStorage.getItem(STORY_KEY)||localStorage.getItem(STORY_KEY))){
    try{await chatRequest('/api/story/state');return;}catch(error){if(error.status!==404)throw error;/* Recreate only expired disposable cloud memory. */}
   }
   // A document load owns one fresh run; StrictMode remounts share this promise.
   const result=await chatRequest('/api/story/workspaces',{});
   sessionStorage.setItem(STORY_KEY,result.workspace_id);
   localStorage.setItem(STORY_KEY,result.workspace_id);
  }
 })().catch(error=>{initialization=null;throw error;});
 return initialization;
}

// Bootstrap only: the original workspace owns every message and control.
export function StoryRouter({Normal}){
 const [ready,setReady]=useState(false),[error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 useEffect(()=>{let active=true;
  async function open(){setError('');try{
   await initialize();
   if(active)setReady(true);
  }catch(e){if(active)setError(e.message);}}
  open();return()=>{active=false;};
 },[attempt]);
 if(error)return <div role="alert" className="workspace-recovery"><strong>We couldn’t open your workspace yet.</strong><p>{error}</p><p>Your onboarding choices are complete. The backend may be starting up. Please retry shortly.</p><button onClick={()=>setAttempt(n=>n+1)}>Retry connection</button></div>;
 return ready?<Normal/>:<div role="status">Opening your workspace…</div>;
}
