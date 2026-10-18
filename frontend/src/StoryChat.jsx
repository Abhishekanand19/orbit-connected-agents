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
 })();
 return initialization;
}

// Bootstrap only: the original workspace owns every message and control.
export function StoryRouter({Normal}){
 const [ready,setReady]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let active=true;
  async function open(){try{
   await initialize();
   if(active)setReady(true);
  }catch(e){if(active)setError(e.message);}}
  open();return()=>{active=false;};
 },[]);
 if(error)return <div role="alert">{error}<button onClick={()=>location.reload()}>Retry connection</button></div>;
 return ready?<Normal/>:<div role="status">Opening your workspace…</div>;
}
