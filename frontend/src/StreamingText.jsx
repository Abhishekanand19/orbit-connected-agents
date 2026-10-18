import React,{useEffect,useRef,useState} from 'react';
const finished=new Set();
// Render text safely; never interpret provider output as HTML.
function inline(text,ready){return text.split(/(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s]+|\*\*[^*]+\*\*|`[^`]+`)/g).map((s,i)=>{
 const link=s.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
 if(link)return ready?<a key={i} href={link[2]} target="_blank" rel="noopener noreferrer">{link[1]}</a>:s;
 if(/^https?:\/\//.test(s))return ready?<a key={i} href={s} target="_blank" rel="noopener noreferrer">{s}</a>:s;
 if(s.startsWith('**')&&s.endsWith('**'))return <strong key={i}>{s.slice(2,-2)}</strong>;
 if(s.startsWith('`')&&s.endsWith('`'))return <code key={i}>{s.slice(1,-1)}</code>;
 return s;
 });}
export default function StreamingText({text='',id,onComplete}){
 const [count,setCount]=useState(()=>finished.has(id)?Infinity:0),ref=useRef(null),done=useRef(onComplete);done.current=onComplete;
 const chunks=text.match(/\S+\s*|\s+/g)||[];
 const complete=count>=chunks.length;
 useEffect(()=>{
  if(finished.has(id)){setCount(Infinity);done.current?.();return;}
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){setCount(Infinity);finished.add(id);done.current?.();return;}
  let n=0;setCount(0);
  const timer=setInterval(()=>{n+=2;setCount(n);if(n>=chunks.length){clearInterval(timer);setCount(Infinity);finished.add(id);done.current?.();}},70);
  return()=>clearInterval(timer);
 },[id]);
 useEffect(()=>{const log=ref.current?.closest('[role=log]');if(log&&log.scrollHeight-log.clientHeight-log.scrollTop<160)log.scrollTop=log.scrollHeight;},[count]);
 return <span ref={ref} className="streaming-text" data-streaming={!complete} aria-busy={!complete}>{inline(complete?text:chunks.slice(0,count).join(''),complete)}</span>;
}
