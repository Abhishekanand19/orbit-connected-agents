import React,{useState,useEffect} from 'react';
import {chatRequest,STORY_KEY} from './services';
import './story.css';

// Bootstrap only: the original workspace owns every message and control.
export function StoryRouter({Normal}){
 const [ready,setReady]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let active=true;
  async function open(){try{
   if(localStorage.getItem('orbit.chat.mode')!=='normal'&&!localStorage.getItem(STORY_KEY)){
    const result=await chatRequest('/api/story/workspaces',{});localStorage.setItem(STORY_KEY,result.workspace_id);
   }
   if(active)setReady(true);
  }catch(e){if(active)setError(e.message);}}
  open();return()=>{active=false;};
 },[]);
 if(error)return <div role="alert">{error}<button onClick={()=>location.reload()}>Retry connection</button></div>;
 return ready?<Normal/>:<div role="status">Opening your workspace…</div>;
}
