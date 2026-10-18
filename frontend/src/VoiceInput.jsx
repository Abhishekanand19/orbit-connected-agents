import React,{useEffect,useRef,useState} from 'react';
import {Mic,Square,X,ArrowUp} from 'lucide-react';

// Recognition completion, not a timer, is the submission boundary.
export default function VoiceInput({draft,setDraft,onActive,onSubmit,busy}){
 const current=useRef(null),canvas=useRef(null),mounted=useRef(true);
 const [phase,setPhase]=useState('idle'),[error,setError]=useState(''),[preview,setPreview]=useState('');
 function clean(s){clearTimeout(s.watchdog);clearTimeout(s.startTimer);clearTimeout(s.finishTimer);cancelAnimationFrame(s.frame);s.stream?.getTracks().forEach(t=>t.stop());if(s.context?.state!=='closed')s.context?.close().catch(()=>{});}
 function abort(s){try{s.recognition?.abort();}catch{/* Already stopped. */}}
 function transcript(s,finalOnly=false){return s.results.filter(v=>v&&(!finalOnly||v.final)).map(v=>v.text.trim()).filter(Boolean).join(' ');}
 function fail(s,message){
  if(current.current!==s||s.cancelled)return;
  s.cancelled=true;s.send=false;current.current=null;abort(s);clean(s);
  if(!mounted.current)return;
  const words=transcript(s);if(words)setDraft([s.base,words].filter(Boolean).join(' '));
  idle();setError(message+(words?' Captured text is in the composer for review.':''));
 }
 function idle(){if(mounted.current){setPhase('idle');setPreview('');onActive(false);}}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;const s=current.current;if(s){s.cancelled=true;abort(s);clean(s);}onActive(false);};},[]);
 async function start(){
  if(current.current||busy)return;
  setError('');setPreview('');
  const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Constructor||!navigator.mediaDevices?.getUserMedia){setError('Speech recognition is unavailable in this browser. Use Edge or Chrome, or type instead.');return;}
  const s={base:draft,results:[],send:true,cancelled:false,frame:0};current.current=s;setPhase('requesting');onActive(true);
  try{
   s.stream=await navigator.mediaDevices.getUserMedia({audio:true});
   if(s.cancelled||!mounted.current){clean(s);return;}
   const Audio=window.AudioContext||window.webkitAudioContext;
   // The optional waveform must never block recognition startup.
   try{if(Audio){s.context=new Audio();s.context.resume().catch(()=>{});s.analyser=s.context.createAnalyser();s.analyser.fftSize=256;s.context.createMediaStreamSource(s.stream).connect(s.analyser);
    const values=new Uint8Array(s.analyser.frequencyBinCount);
    const draw=()=>{if(s.cancelled)return;const c=canvas.current,ctx=c?.getContext('2d');if(ctx){s.analyser.getByteFrequencyData(values);ctx.clearRect(0,0,c.width,c.height);ctx.fillStyle='#bcb7b2';for(let i=0;i<48;i++){const h=2+values[i*2]/255*28;ctx.fillRect(i*c.width/48,(c.height-h)/2,3,h);}}s.frame=requestAnimationFrame(draw);};draw();
   }}catch{/* Recording still works without a waveform. */}
   if(s.cancelled){clean(s);return;}
   const r=new Constructor();s.recognition=r;r.lang=localStorage.getItem('orbit.speech.language')||'en-IN';r.continuous=false;r.interimResults=true;
   s.startTimer=setTimeout(()=>fail(s,'Speech recognition did not start. Retry or use another browser.'),15000);
   r.onstart=()=>{if(!s.cancelled&&current.current===s){clearTimeout(s.startTimer);setPhase('listening');s.watchdog=setTimeout(()=>fail(s,'Recording timed out. Retry or type instead.'),90000);}};
   r.onresult=e=>{if(s.cancelled||current.current!==s)return;s.results.length=e.results.length;for(let i=e.resultIndex;i<e.results.length;i++)s.results[i]={text:e.results[i][0].transcript,final:e.results[i].isFinal};setPreview(transcript(s));};
   // Use the provider's utterance boundary, never a guessed silence delay.
   r.onspeechend=()=>{if(current.current===s&&!s.cancelled)finish(s.send);};
   r.onerror=e=>fail(s,{'not-allowed':'Allow microphone access in browser settings, then retry.','service-not-allowed':'The browser speech service is unavailable or blocked. Try Chrome or type instead.','audio-capture':'No microphone found. Check your input device.','no-speech':'No speech detected. Check your input device and retry.','language-not-supported':'The speech service does not support the selected language.','network':'Speech service could not connect. Check your connection or try another browser.'}[e.error]||'Speech recognition was interrupted. Retry or type instead.');
   r.onend=async()=>{
    clean(s);if(current.current!==s)return;current.current=null;
    if(s.cancelled||!mounted.current)return;
    const words=transcript(s,true),captured=transcript(s);
    const text=[s.base,words].filter(Boolean).join(' ');
    if(s.send&&words&&!s.results.some(v=>v&&!v.final&&v.text.trim())){setPhase('sending');onActive(false);try{await onSubmit(text,'voice_transcript');}catch{if(mounted.current){setDraft(text);setError('Message could not be sent. Your transcript is saved for retry.');}}finally{idle();}}
    else {if(captured)setDraft([s.base,captured].filter(Boolean).join(' '));idle();if(captured!==words)setError('Speech was not finalized. Review the captured text before sending.');else if(!words)setError('No finalized speech received. Retry or type instead.');}
   };
   r.start();
  }catch(e){fail(s,e.name==='NotAllowedError'?'Allow microphone access in browser settings, then retry.':e.name==='NotFoundError'?'No microphone found. Check your input device.':e.name==='NotReadableError'?'Microphone is busy or unavailable. Check Windows input settings and retry.':'Microphone could not start. Retry or type instead.');}
 }
 function finish(send){const s=current.current;if(!s?.recognition||s.finishing)return;s.finishing=true;s.send=send;setPhase('finalizing');s.finishTimer=setTimeout(()=>fail(s,'Speech service did not finish. Nothing was sent.'),5000);try{s.recognition.stop();}catch{fail(s,'Speech recognition stopped unexpectedly. Nothing was sent.');}}
 function cancel(){const s=current.current;if(!s)return;s.cancelled=true;current.current=null;abort(s);clean(s);setDraft(s.base);idle();setError('');}
 const active=phase!=='idle';
 return <div className={`voice-input ${active?'active':''}`} data-voice-state={phase}>
  {active?<><button type="button" className="icon-button" aria-label="Cancel recording" onClick={cancel} disabled={phase==='sending'}><X size={19}/></button>{phase==='requesting'&&<span className="voice-permission">Waiting for microphone permission…</span>}<canvas hidden={phase==='requesting'} ref={canvas} width="480" height="36" aria-label="Live microphone amplitude"/><span className="sr-only" role="status">{phase}</span><button type="button" className="icon-button" aria-label="Stop recording" disabled={phase!=='listening'} onClick={()=>finish(false)}><Square size={17}/></button><button type="button" className="voice-send" aria-label="Send recording" disabled={phase!=='listening'} onClick={()=>finish(true)}><ArrowUp size={20}/></button></>:<button type="button" className="icon-button" aria-label="Start microphone" disabled={busy} onClick={start}><Mic size={20}/></button>}
  {preview&&active&&<div className="voice-preview" aria-live="polite">{preview}</div>}
  {error&&<div className="voice-error" role="alert">{error}<button type="button" aria-label="Dismiss microphone error" onClick={()=>setError('')}><X size={13}/></button></div>}
 </div>;
}
