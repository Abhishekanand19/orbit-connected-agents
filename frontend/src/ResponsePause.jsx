import React,{useEffect,useState} from 'react';
export function Thinking(){return <span className="thinking-ring" role="status" aria-label="Preparing response presentation">{Array.from({length:8},(_,i)=><i key={i} style={{transform:`rotate(${i*45}deg) translateY(-7px)`,opacity:.25+i*.09}}/>)}</span>;}
const shown=new Set();
export default function ResponsePause({id,until,children}){
 const [ready,setReady]=useState(()=>shown.has(id)||Date.now()>=until);
 useEffect(()=>{const timer=setTimeout(()=>{shown.add(id);setReady(true);},matchMedia('(prefers-reduced-motion: reduce)').matches?0:Math.max(0,until-Date.now()));return()=>clearTimeout(timer);},[id,until]);
 return ready?children:<Thinking/>;
}
