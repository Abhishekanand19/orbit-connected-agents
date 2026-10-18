import React,{useEffect,useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Check,ExternalLink,ShieldCheck} from 'lucide-react';
import './onboarding.css';
const COMPLETE='orbit.onboarding.complete.v1';
function completed(){try{return localStorage.getItem(COMPLETE)==='true';}catch{return false;}}
const apps=[['gmail','Gmail'],['drive','Google Drive'],['calendar','Google Calendar'],['tasks','Google Tasks'],['slack','Slack'],['excel','Microsoft Excel'],['teams','Microsoft Teams']];
function Mark({word=false}){return <span className="onboarding-brand"><img src="/brand/orbit-symbol.svg" alt="Orbit"/>{word&&<span>orbit<span>.</span></span>}</span>;}
function AppIcon({id}){
 if(id==='gmail')return <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M4 26V8l12 9L28 8v18" fill="none" stroke="#4285f4" strokeWidth="6" strokeLinejoin="round"/><path d="M4 8l12 9L28 8" fill="none" stroke="#ea4335" strokeWidth="6"/><path d="M28 9v17" stroke="#34a853" strokeWidth="6"/></svg>;
 if(id==='drive')return <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M12 3h9L7 27 2 19z" fill="#0f9d58"/><path d="M12 3h9l10 17h-9z" fill="#fbbc04"/><path d="M7 27l5-8h19l-5 8z" fill="#4285f4"/></svg>;
 if(id==='slack')return <svg viewBox="0 0 32 32" aria-hidden="true"><g fill="#36c5f0"><rect x="2" y="10" width="12" height="5" rx="2.5"/><circle cx="11.5" cy="5.5" r="2.5"/></g><g fill="#2eb67d"><rect x="18" y="2" width="5" height="12" rx="2.5"/><circle cx="27" cy="11.5" r="2.5"/></g><g fill="#ecb22e"><rect x="18" y="18" width="12" height="5" rx="2.5"/><circle cx="20.5" cy="27" r="2.5"/></g><g fill="#e01e5a"><rect x="10" y="18" width="5" height="12" rx="2.5"/><circle cx="5.5" cy="20.5" r="2.5"/></g></svg>;
 return <span className={`service-icon ${id}`}>{id==='calendar'?'31':id==='tasks'?<Check size={25}/>:id==='excel'?'X':'T'}</span>;
}
export function WelcomeGate({children}){
 const [complete,setComplete]=useState(completed);
 const [launched,setLaunched]=useState(false),[launchError,setLaunchError]=useState(''),popup=useRef(null);
 const welcome=location.pathname==='/welcome';
 useEffect(()=>{const sync=e=>{if(e.key===COMPLETE)setComplete(e.newValue==='true');};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync);},[]);
 if(welcome)return <Onboarding/>;
 if(complete&&!launched)return children;
 return <div className="welcome-launch"><Mark word/><h1>{launched?'Your welcome tab is ready.':'A little space for your bigger picture.'}</h1><p>{launched?'Finish setup there. That tab will become your Orbit workspace.':'Welcome to Orbit. Start with a quick introduction and choose the apps you want to connect.'}</p><button className="onboard-primary" onClick={()=>{if(popup.current&&!popup.current.closed){popup.current.focus();return;}popup.current=window.open(complete?'/':'/welcome','orbit-welcome');if(popup.current){setLaunched(true);setLaunchError('');}else setLaunchError('The browser blocked the welcome tab. Allow popups for this local site and try again.');}}>{launched?'Go to Orbit tab':'Get started in a new tab'}<ExternalLink size={18}/></button>{launchError&&<p role="alert">{launchError}</p>}<small>{launched?'This launch tab stays separate from your workspace.':'Opens a separate welcome tab. Your existing memory stays safe.'}</small></div>;
}
function Onboarding(){
 const [step,setStep]=useState(()=>new URLSearchParams(location.search).get('step')==='apps'?'apps':'welcome');
 const [selected,setSelected]=useState({}),[leaving,setLeaving]=useState(false),[error,setError]=useState('');
 const timer=useRef(null);
 useEffect(()=>()=>clearTimeout(timer.current),[]);
 function go(next){history.replaceState({},'',next==='apps'?'/welcome?step=apps':'/welcome');setStep(next);}
 function finish(){try{localStorage.setItem(COMPLETE,'true');}catch{setError('Browser storage is unavailable. Allow local storage to finish setup.');return;}setLeaving(true);timer.current=setTimeout(()=>location.replace('/'),matchMedia('(prefers-reduced-motion: reduce)').matches?0:350);}
 return <main className={`onboarding ${step==='apps'?'apps-page':'welcome-page'} ${leaving?'leaving':''}`}>
 {step==='welcome'?<>
  <div className="signin-demo-notice"><Mark word/><span id="demo-input-note">Demo preview · No Google authentication</span></div>
  <section className="signin-reference" aria-label="Demonstration sign-in layout"><h1 className="visually-hidden">Sign in — Orbit demo</h1>
   <img src="/brand/signin-reference.png" alt="Google sign-in visual reference used for the Orbit demonstration"/>
   <form onSubmit={e=>{e.preventDefault();e.currentTarget.reset();go('apps');}} autoComplete="off">
    <label className="signin-demo-field"><span>Email or phone</span><input aria-label="Email or phone" aria-describedby="demo-input-note" type="text" inputMode="email" autoComplete="off" spellCheck={false}/></label>
    <button className="signin-demo-next" type="submit">Next</button>
   </form>
  </section>
 </>:<div className="apps-container">
  <header className="apps-header"><Mark word/><button className="onboard-back" onClick={()=>go('welcome')}><ArrowLeft size={16}/>Back</button></header>
  <section className="ecosystem"><div className="ecosystem-heading"><span className="onboard-eyebrow">BETTER TOGETHER</span><h1>Your world, connected.</h1><p>Bring the tools you use into the conversations that matter.</p></div><img className="ecosystem-illustration" src="/brand/orbit-ecosystem.png" alt="Orbit surrounded by Gmail, Google Drive, Google Calendar, Google Tasks, Slack, Microsoft Excel and Microsoft Teams"/><p className="ecosystem-caption">An illustration of the ecosystem.</p></section>
  <section className="connectors"><div className="connections-heading"><div><h2>Your connections</h2><p id="preview-controls-note">Preview controls only — these selections are not real authorization status.</p></div></div>
   <div className="connector-list">{apps.map(([id,name])=><div className="connector-row" key={id} data-service={id}><div className="connector-icon"><AppIcon id={id}/></div><div className="connector-name"><strong>{name}</strong></div><div className="connector-action"><span className="connection-label">{selected[id]?'Connected':'Not Connected'}</span><button type="button" role="switch" aria-label={`${name} preview connection`} aria-describedby="preview-controls-note" aria-checked={!!selected[id]} className={`connection-switch demo-switch ${selected[id]?'on':''}`} onClick={()=>setSelected(s=>({...s,[id]:!s[id]}))}><span/></button></div></div>)}</div>
   <div className="connections-bottom"><p><ShieldCheck size={17}/>Demo selections never change provider permissions or send anything.</p><button className="onboard-primary" disabled={leaving} onClick={finish}>Continue to Orbit<ArrowRight size={18}/></button></div><small className="optional-connections">Actual Gmail, Calendar and Slack authorization remains separate and unchanged.</small>{error&&<p role="alert">{error}</p>}
  </section>
 </div>}
 </main>;
}
