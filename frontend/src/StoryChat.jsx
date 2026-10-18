import React,{useState,useEffect} from 'react';
import {chatRequest,STORY_KEY} from './services';
import './story.css';

let initialization;
function initialize(){
 if(!initialization)initialization=(async()=>{
  if(localStorage.getItem('orbit.chat.mode')!=='normal'){
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
 if(error)return <div role="alert" className="workspace-recovery"><strong>We couldn’t open your workspace yet.</strong><p>{error}</p><p>Your onboarding choices are complete. Check that Orbit’s backend is running on port 8001, then retry.</p><button onClick={()=>setAttempt(n=>n+1)}>Retry connection</button></div>;
 return ready?<Normal/>:<div role="status">Opening your workspace…</div>;
}
