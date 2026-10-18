import React,{useEffect,useRef,useState} from 'react';
import {Mic,Square,X,ArrowUp} from 'lucide-react';

// Recognition completion, not a timer, is the submission boundary.
export default function VoiceInput({draft,setDraft,onActive,onSubmit,busy}){
 const current=useRef(null),canvas=useRef(null),mounted=useRef(true);
 const [phase,setPhase]=useState('idle'),[error,setError]=useState(''),[preview,setPreview]=useState('');
 function clean(s){clearTimeout(s.watchdog);cancelAnimationFrame(s.frame);s.stream?.getTracks().forEach(t=>t.stop());s.context?.close().catch(()=>{});}
 function idle(){if(mounted.current){setPhase('idle');setPreview('');onActive(false);}}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;const s=current.current;if(s){s.cancelled=true;s.recognition?.abort();clean(s);}onActive(false);};},[]);
 useEffect(()=>{if(phase==='idle')setError('');},[draft]);
 async function start(){
  if(current.current||busy)return;
  setError('');setPreview('');
  const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Constructor||!navigator.mediaDevices?.getUserMedia){setError('Speech recognition is unavailable in this browser. Use Edge or Chrome, or type instead.');return;}
  const s={base:draft,results:[],send:false,cancelled:false,frame:0};current.current=s;setPhase('requesting');onActive(true);
  try{
   s.stream=await navigator.mediaDevices.getUserMedia({audio:true});
   if(s.cancelled||!mounted.current){clean(s);return;}
   const Audio=window.AudioContext||window.webkitAudioContext;
   if(Audio){s.context=new Audio();await s.context.resume();s.analyser=s.context.createAnalyser();s.analyser.fftSize=256;s.context.createMediaStreamSource(s.stream).connect(s.analyser);
    const values=new Uint8Array(s.analyser.frequencyBinCount);
    const draw=()=>{if(s.cancelled)return;const c=canvas.current,ctx=c?.getContext('2d');if(ctx){s.analyser.getByteFrequencyData(values);ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#bcb7b2';for(let i=0;i<48;i++){const h=2+values[i*2]/255*28;ctx.fillRect(i*c.width/48,(c.height-h)/2,3,h);}}s.frame=requestAnimationFrame(draw);};draw();
   }
   if(s.cancelled){clean(s);return;}
   const r=new Constructor();s.recognition=r;r.lang=localStorage.getItem('orbit.speech.language')||'en-IN';r.continuous=true;r.interimResults=true;
   r.onstart=()=>{if(!s.cancelled){setPhase('listening');s.watchdog=setTimeout(()=>{s.failed=true;s.send=false;r.abort();clean(s);if(current.current===s){current.current=null;idle();setError('Recording timed out. Retry or type instead.');}},90000);}};
   r.onresult=e=>{if(s.cancelled)return;for(let i=e.resultIndex;i<e.results.length;i++)s.results[i]={text:e.results[i][0].transcript,final:e.results[i].isFinal};setPreview(s.results.map(v=>v?.text||'').join(' '));};
   r.onerror=e=>{if(s.cancelled)return;s.failed=true;s.send=false;setError({'not-allowed':'Allow microphone access in browser settings, then retry.','audio-capture':'No microphone found. Check your input device.','no-speech':'No speech detected. Retry or type instead.','network':'Speech service could not connect. Retry or type instead.'}[e.error]||'Speech recognition was interrupted. Retry or type instead.');clean(s);};
   r.onend=async()=>{
    clean(s);if(current.current!==s)return;current.current=null;
    if(s.cancelled||!mounted.current)return;
    const words=s.results.filter(v=>v?.final).map(v=>v.text.trim()).join(' ').trim();
    const text=[s.base,words].filter(Boolean).join(' ');
    if(s.send&&!s.failed&&words){setPhase('sending');onActive(false);await onSubmit(text,'voice_transcript');idle();}
    else {if(words)setDraft(text);if(!words&&!s.failed)setError('No finalized speech received. Retry or type instead.');idle();}
   };
   r.start();
  }catch(e){clean(s);if(s.cancelled)return;current.current=null;idle();setError(e.name==='NotAllowedError'?'Allow microphone access in browser settings, then retry.':e.name==='NotFoundError'?'No microphone found. Check your input device.':'Microphone could not start. Retry or type instead.');}
 }
 function finish(send){const s=current.current;if(!s?.recognition||s.finishing)return;s.finishing=true;s.send=send;setPhase('finalizing');s.recognition.stop();}
 function cancel(){const s=current.current;if(!s)return;s.cancelled=true;current.current=null;s.recognition?.abort();clean(s);setDraft(s.base);idle();setError('');}
 const active=phase!=='idle';
 return <div className={`voice-input ${active?'active':''}`} data-voice-state={phase}>
  {active?<><button type="button" className="icon-button" aria-label="Cancel recording" onClick={cancel} disabled={phase==='sending'}><X size={19}/></button>{phase==='requesting'&&<span className="voice-permission">Waiting for microphone permission…</span>}<canvas hidden={phase==='requesting'} ref={canvas} width="480" height="36" aria-label="Live microphone amplitude"/><span className="sr-only" role="status">{phase}</span><button type="button" className="icon-button" aria-label="Stop recording" disabled={phase!=='listening'} onClick={()=>finish(false)}><Square size={17}/></button><button type="button" className="voice-send" aria-label="Send recording" disabled={phase!=='listening'} onClick={()=>finish(true)}><ArrowUp size={20}/></button></>:<button type="button" className="icon-button" aria-label="Start microphone" disabled={busy} onClick={start}><Mic size={20}/></button>}
  {preview&&active&&<div className="voice-preview" aria-live="polite">{preview}</div>}
  {error&&<div className="voice-error" role="alert">{error}<button type="button" aria-label="Dismiss microphone error" onClick={()=>setError('')}><X size={13}/></button></div>}
 </div>;
}
