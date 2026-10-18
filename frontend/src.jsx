import StreamingText from './src/StreamingText';
import ResizeHandle from './src/ResizeHandle';
import ProgressiveHandoffs from './src/ProgressiveHandoffs';
import React, {lazy, Suspense, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Orbit, Plus, Search, ArrowUp, SlidersHorizontal, X, PanelLeft, Check, ChevronRight, MessageSquare, Unplug, RotateCcw, ArrowUpRight, LockKeyhole, Network, GitFork} from 'lucide-react';
import Avatar from './src/Avatar';
import {WelcomeGate} from './src/Onboarding';


import VoiceInput from './src/VoiceInput';
import ComposerTools,{filePayload} from './src/ComposerTools';
import ApprovalPanel from './src/ApprovalPanel';
import StoryTaskMessage from './src/StoryTaskMessage';
import {StoryRouter} from './src/StoryChat';
import {colors, freshWorkspace, loadWorkspace, saveWorkspace, chatService, chatRequest, messageFromApi, defaults, STORY_KEY, displayName} from './src/services';
import './style.css';
import './refinement.css';
const agentSubtitles={coordinator:'Manages all agents',planner:'Plans actions & keeps notes',research:'Finds information',communication:'Handles messages & replies',tasks:'Creates & tracks tasks'};
const GraphWorkspace = lazy(() => import('./src/graph/GraphWorkspace'));

function AvatarPicker({value, onChange}) {
 return <div className="avatar-picker"><span className="field-label">Shape</span><div className="shapes">{['Bloom', 'Cubby', 'Sage', 'Chatter', 'Pebble'].map((name, shape)=><button key={name} type="button" title={name} aria-label={`${name} avatar`} aria-pressed={value.shape===shape} onClick={()=>onChange({shape})}><Avatar shape={shape} color={value.color} size={42}/></button>)}</div><span className="field-label color-label">Color</span><div className="colors">{colors.map((color,i)=><button type="button" key={color} style={{background:color}} aria-label={['Coral','Lilac','Sage','Honey','Sky','Rose'][i]} aria-pressed={value.color===color} onClick={()=>onChange({color})}>{value.color===color&&<Check size={14}/>}</button>)}</div></div>;
}
function Modal({children, title, close}) {
 const ref=useRef(null);
 useEffect(()=>{const prior=document.activeElement; ref.current.showModal(); return()=>prior?.focus();},[]);
 return <dialog ref={ref} onCancel={close} onClick={e=>{if(e.target===ref.current)close();}}><div className="modal-inner"><button className="icon-button modal-close" aria-label="Close dialog" onClick={close}><X size={20}/></button><h2>{title}</h2>{children}</div></dialog>;
}
function CreateBot({close, create}) {
 const [draft,setDraft]=useState({name:'',description:'',instructions:'',shape:0,color:colors[0],notifications:false});
 const update=patch=>setDraft(d=>({...d,...patch}));
 return <Modal title="A new member of your orbit." close={close}><p className="muted">Give your bot a purpose. And a little personality.</p><form onSubmit={e=>{e.preventDefault();if(draft.name.trim()&&draft.description.trim())create({...draft,name:draft.name.trim(),description:draft.description.trim()});}}><div className="creation-preview"><Avatar {...draft} size={100}/><span>{draft.name||'Your next great sidekick'}</span></div><label>Bot name<input autoFocus required maxLength={60} placeholder="e.g. Writing Companion" value={draft.name} onChange={e=>update({name:e.target.value})}/></label><label>Purpose<textarea required maxLength={240} rows={2} placeholder="What would you like this bot to help with?" value={draft.description} onChange={e=>update({description:e.target.value})}/></label><AvatarPicker value={draft} onChange={update}/><div className="modal-actions"><button type="button" className="secondary" onClick={close}>Cancel</button><button className="primary" disabled={!draft.name.trim()||!draft.description.trim()}>Create bot <ArrowUpRight size={16}/></button></div></form></Modal>;
}
function Settings({bot, update, close, persist}) {
 const [saved,setSaved]=useState(false);
 useEffect(()=>{setSaved(false);},[bot]);
 return <aside className="settings"><div className="panel-title"><span>Bot settings</span><button className="icon-button" onClick={close} aria-label="Close settings"><X size={18}/></button></div><div className="settings-scroll"><div className="profile"><div className="avatar-stage"><Avatar {...bot} size={102}/></div><span className="eyebrow">A PERSONALITY OF ITS OWN</span></div><button className="secondary" onClick={async()=>{localStorage.setItem('orbit.chat.mode','deterministic');location.reload();}}>Fresh isolated demo</button><label className="conversation-mode">Conversation engine<select aria-label="Conversation engine" value={localStorage.getItem('orbit.chat.mode')||'deterministic'} onChange={e=>{localStorage.setItem('orbit.chat.mode',e.target.value);location.reload();}}><option value="deterministic">Family planning · deterministic</option><option value="normal">Normal · configured AI provider</option></select></label><form onSubmit={e=>{e.preventDefault();setSaved(persist());}}><label>Name<input required maxLength={60} value={bot.name} onChange={e=>update({name:e.target.value})} onBlur={()=>{if(!bot.name.trim())update({name:'Untitled bot'});}}/></label><label>Purpose<textarea maxLength={240} rows={3} value={bot.description} onChange={e=>update({description:e.target.value})}/></label><label>Instructions <span className="optional">/ personality</span><textarea maxLength={4000} rows={4} placeholder="How should this bot approach its work?" value={bot.instructions} onChange={e=>update({instructions:e.target.value})}/></label><p className="field-note">Used for this bot’s responses.</p><AvatarPicker value={bot} onChange={update}/><div className="notification"><div><strong>Notifications</strong><p>Preference only. Delivery comes later.</p></div><button type="button" className={`toggle ${bot.notifications?'on':''}`} role="switch" aria-checked={bot.notifications} aria-label="Notifications" onClick={()=>update({notifications:!bot.notifications})}><span/></button></div><button className="save-button" type="submit">{saved?<Check size={16}/>:<SlidersHorizontal size={15}/>} {saved?'Settings saved':'Save settings'}</button><p className="save-note" aria-live="polite">{saved?'Your changes are saved in this browser.':'Changes are saved automatically.'}</p></form></div><div className="panel-footer"><LockKeyhole size={13}/> Your space. Stored on this device.</div></aside>;
}
function App(){
 const [initial]=useState(()=>{try{return loadWorkspace(window.localStorage);}catch{return {data:freshWorkspace(),error:'Browser storage is unavailable. Changes are only kept in this tab.',blocked:true};}});
 const [workspace,setWorkspace]=useState({...initial.data,selectedId:'coordinator',conversations:{}}), [storageError,setStorageError]=useState(initial.error),[query,setQuery]=useState(''),[creating,setCreating]=useState(false),[settings,setSettings]=useState(false),[sidebar,setSidebar]=useState(false),[clearing,setClearing]=useState(false),[drafts,setDrafts]=useState({});
 const [workspaceMenu,setWorkspaceMenu]=useState(false);
 const [rail,setRail]=useState(()=>localStorage.getItem('orbit.sidebar.collapsed')==='true');
 const [capturing,setCapturing]=useState(false);
 const [depth,setDepth]=useState(()=>localStorage.getItem('orbit.response.depth')||'high');
 const uploadCache=useRef(new WeakMap());
 const [files,setFiles]=useState([]),[source,setSource]=useState('typed');
 const [leftWidth,setLeftWidth]=useState(()=>Number(localStorage.getItem('orbit.sidebar.width'))||260);
 const [split,setSplit]=useState(()=>Number(localStorage.getItem('orbit.graph.width'))||520);
 const [viewport,setViewport]=useState(innerWidth),[revealed,setRevealed]=useState({});
 useEffect(()=>{const resize=()=>setViewport(innerWidth);addEventListener('resize',resize);return()=>removeEventListener('resize',resize);},[]);
 const effectiveLeft=rail?76:Math.max(190,Math.min(leftWidth,360,viewport-720));
 const graphMax=Math.max(300,viewport-effectiveLeft-(settings?290:0)-360);
 const graphWidth=Math.min(Math.max(300,split),graphMax);
 const resizeLeft=n=>{const width=Math.max(190,Math.min(n,360,viewport-720));setLeftWidth(width);localStorage.setItem('orbit.sidebar.width',String(width));};
 const resizeGraph=n=>{const width=Math.max(300,Math.min(n,graphMax));setSplit(width);localStorage.setItem('orbit.graph.width',String(width));};
 const deterministic=localStorage.getItem('orbit.chat.mode')!=='normal';
 const [graphMode,setGraphMode]=useState(null),[graphRoot,setGraphRoot]=useState('');
 const [busy,setBusy]=useState(false),[chatError,setChatError]=useState(''),[activity,setActivity]=useState({});
 const pending=useRef({}),conversationIds=useRef({}),sending=useRef(false);
 const end=useRef(null), composer=useRef(null);
 const bot=workspace.bots.find(b=>b.id===workspace.selectedId)||workspace.bots[0];
 const messages=workspace.conversations[bot.id]||[], draft=drafts[bot.id]||'';
 const persist=()=>{if(initial.blocked)return false;const saved=deterministic?{...initial.data,bots:workspace.bots}:workspace;const error=saveWorkspace(window.localStorage,saved);setStorageError(error);return !error;};
 useEffect(()=>{persist();},[workspace]);
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth',block:'end'});},[bot.id,messages.length]);
 useEffect(()=>{const escape=e=>{if(e.key==='Escape'){setSidebar(false);setSettings(false);}};document.addEventListener('keydown',escape);return()=>document.removeEventListener('keydown',escape);},[]);
 useEffect(()=>{setFiles([]);setSource('typed');},[bot.id]);
 function updateBot(patch){setWorkspace(w=>({...w,bots:w.bots.map(b=>b.id===bot.id?{...b,...patch}:b)}));}
 useEffect(()=>{
   let cancelled=false;
   if(deterministic)return;
   chatRequest('/api/chat/bots/'+encodeURIComponent(bot.id)+'/latest').then(data=>{
     if(cancelled||sending.current||capturing)return;
     if(data.conversation_id){const lastUser=[...data.messages].reverse().find(m=>m.properties.role==='user');if(lastUser)chatRequest('/api/chat/activity/'+encodeURIComponent(lastUser.id)).then(result=>{if(!cancelled)setActivity(a=>({...a,[bot.id]:(result.activity||[]).map(r=>r.properties.owner+': '+r.properties.status).join(' · ')}));}).catch(()=>{});const last=data.messages.at(-1);if(last?.properties.role==='user'){pending.current[bot.id]=messageFromApi(last);setDrafts(d=>({...d,[bot.id]:last.properties.content}));}conversationIds.current[bot.id]=data.conversation_id;setWorkspace(w=>({...w,conversations:{...w.conversations,[bot.id]:data.messages.map(messageFromApi)}}));}
   }).catch(()=>{if(!cancelled)setChatError('Cannot load saved chat. Check the backend connection.');});
   return()=>{cancelled=true;};
 },[bot.id]);
 useEffect(()=>{const load=()=>chatRequest('/api/chat/bots/coordinator/latest').then(data=>{if(!data.conversation_id)return;conversationIds.current.coordinator=data.conversation_id;pending.current.coordinator=null;setWorkspace(w=>({...w,selectedId:'coordinator',conversations:{...w.conversations,coordinator:data.messages.map(messageFromApi)}}));setGraphRoot('family:appointment');}).catch(e=>setChatError(e.message));window.addEventListener('orbit:demo-session',load);return()=>window.removeEventListener('orbit:demo-session',load);},[]);
 async function send(spoken=null,spokenSource=null){
   if((!(spoken??draft).trim()&&!files.length)||sending.current||(capturing&&!spoken))return;
   const id=bot.id,content=(spoken??draft).trim()||'Please keep these attachments with this conversation.';
   const message=pending.current[id]?.content===content?pending.current[id]:chatService.createMessage(content);
   pending.current[id]=message;
   const legacy=!conversationIds.current[id]?(workspace.conversations[id]||[]).map(m=>({id:m.id,role:m.role,content:m.content})):[];
   const conversation=conversationIds.current[id]||(conversationIds.current[id]='chat:'+crypto.randomUUID());
   sending.current=true;setBusy(true);setChatError('');
   setWorkspace(w=>({...w,conversations:{...w.conversations,[id]:[...(w.conversations[id]||[]).filter(m=>m.id!==message.id),message]}}));
   try{
     const attachments=[];for(const file of files){let uploaded=uploadCache.current.get(file);if(!uploaded){uploaded=await chatRequest('/api/attachments',await filePayload(file));uploadCache.current.set(file,uploaded);}attachments.push(uploaded);}
     const result=await chatRequest('/api/chat',{id:message.id,bot_id:id,name:bot.name,instructions:bot.instructions,conversation_id:conversation,content,legacy_messages:deterministic?[]:legacy,source:spokenSource||source,response_depth:depth,attachment_ids:attachments.map(a=>a.id)});
     setActivity(a=>({...a,[id]:(result.activity||[]).map(r=>r.properties.owner+': '+r.properties.status).join(' · ')}));
     const additions=[result.user,result.assistant].map(messageFromApi);if(result.mode==='deterministic'){const {graph,user,assistant,...metadata}=result;additions[1].story=metadata;}setGraphRoot(result.mode==='deterministic'?(result.graph.nodes.some(n=>n.id==='story:appointment')?'story:appointment':'story:aarav'):graphRoot);
     setWorkspace(w=>({...w,conversations:{...w.conversations,[id]:[...(w.conversations[id]||[]).filter(m=>!additions.some(a=>a.id===m.id)),...additions]}}));
     setFiles([]);setSource('typed');setDrafts(d=>({...d,[id]:''}));delete pending.current[id];
     window.dispatchEvent(new Event('orbit:graph-changed'));
   }catch(e){setChatError(e.message||'Chat unavailable. Retry the message.');window.dispatchEvent(new Event('orbit:graph-changed'));}
   finally{sending.current=false;setBusy(false);composer.current?.focus();}
 }

 async function newChat(){
  if(busy)return;setBusy(true);setChatError('');
  try{
   const id='chat:'+crypto.randomUUID();
   await chatRequest(deterministic?'/api/story/conversations':'/api/conversations',{id,bot_id:'chatbot:'+bot.id,title:'New conversation'});
   conversationIds.current[bot.id]=id;delete pending.current[bot.id];
   setWorkspace(w=>({...w,conversations:{...w.conversations,[bot.id]:[]}}));setDrafts(d=>({...d,[bot.id]:''}));setActivity({});setGraphRoot('');setFiles([]);setSource('typed');
  }catch(e){setChatError(e.message);}finally{setBusy(false);}
 }

 return <div style={{'--graph-width':graphWidth+'px','--sidebar-width':effectiveLeft+'px'}} className={`app ${settings?'with-settings':''} ${rail?'rail':''} ${graphMode?'with-graph':''}`}>
 {sidebar&&<button className="mobile-shade" aria-label="Close bot list" onClick={()=>setSidebar(false)}/>}
 <aside className={`sidebar ${sidebar?'mobile-open':''}`}>{!rail&&<ResizeHandle side="left" value={effectiveLeft} onChange={resizeLeft}/>}<div className="brand"><img className="official-brand" src="/brand/orbit-symbol.svg" alt="Orbit"/><span>orbit<span className="brand-dot">.</span></span><button className="icon-button collapse-sidebar" aria-label={rail?'Expand sidebar':'Collapse sidebar'} onClick={()=>{setRail(v=>{localStorage.setItem('orbit.sidebar.collapsed',String(!v));return !v;});}}><PanelLeft size={18}/></button><button className="icon-button mobile-only" aria-label="Close bots" onClick={()=>setSidebar(false)}><X size={18}/></button></div><div className="workspace-label">YOUR PERSONAL ORBIT</div><div className="search"><button className="icon-button" aria-label="Search bots" onClick={()=>{setRail(false);setTimeout(()=>document.querySelector('.search input')?.focus(),0);}}><Search size={16}/></button><input aria-label="Search bots" placeholder="Find a bot…" value={query} onChange={e=>setQuery(e.target.value)}/><span>/</span></div><div className="bot-list-title"><span>Your bots <span className="count">{workspace.bots.length}</span></span><button className="add-button" aria-label="Create new bot" title="Create new bot" onClick={()=>setCreating(true)}><Plus size={18}/></button></div><nav className="bot-list" aria-label="Your bots">{workspace.bots.filter(b=>`${b.name} ${b.description}`.toLowerCase().includes(query.toLowerCase())).map(b=><button key={b.id} title={b.name} aria-label={b.name} className={`bot-item ${bot.id===b.id?'selected':''}`} aria-current={bot.id===b.id?'true':undefined} onClick={()=>{setWorkspace(w=>({...w,selectedId:b.id}));setSidebar(false);}}><Avatar {...b}/><span className="bot-copy"><strong>{b.name||'Untitled bot'}</strong><span>{b.description||'Make it your own.'}</span></span>{bot.id===b.id&&<span className="selected-dot"/>}</button>)}{!workspace.bots.some(b=>`${b.name} ${b.description}`.toLowerCase().includes(query.toLowerCase()))&&<p className="no-results">No bots found. Try another name.</p>}</nav><button className="invite-bot" onClick={()=>setCreating(true)}><Plus size={16}/> Make room for another bot</button><div className="workspace-menu-wrap">{workspaceMenu&&<div className="workspace-menu" role="menu"><button role="menuitem" onClick={()=>setWorkspaceMenu(false)}>Workspace</button><button role="menuitem" onClick={()=>{localStorage.removeItem('orbit.onboarding.complete.v1');location.assign('/welcome');}}>Restart onboarding</button></div>}<button className="sidebar-bottom" aria-label="Abhishek Anand workspace menu" aria-expanded={workspaceMenu} onClick={()=>setWorkspaceMenu(v=>!v)}><div className="local-avatar">A</div><div><strong>Abhishek Anand</strong><span>Plus subscription</span></div><LockKeyhole size={15}/></button></div></aside>
 <div className="workspace-body"><main className="chat"><header className="chat-header"><button className="icon-button mobile-only" onClick={()=>setSidebar(true)} aria-label="Open bots"><PanelLeft size={19}/></button><Avatar {...bot} size={38}/><div className="header-name"><h1>{bot.name||'Untitled bot'}</h1><span>{agentSubtitles[bot.id]||bot.description}</span>{busy&&<span role="status">Updating your plan...</span>}</div><div className="header-actions"><button className="graph-launch" aria-label="New Chat" disabled={busy} onClick={newChat}><Plus size={17}/><span>New Chat</span></button><button className="graph-launch" aria-label="Open Graph View" title="Graph View" onClick={()=>setGraphMode('network')}><Network size={17}/><span>Graph View</span></button><button className="graph-launch" aria-label="Open Simple View" title="Simple View" onClick={()=>setGraphMode('simple')}><GitFork size={17}/><span>Simple View</span></button><span className="divider"/><button className={`icon-button ${settings?'active':''}`} title="Bot settings" aria-label="Toggle bot settings" aria-expanded={settings} onClick={()=>setSettings(s=>!s)}><SlidersHorizontal size={19}/></button></div></header>
 {chatError&&<div role="alert" className="storage-error">{chatError}</div>}{storageError&&<div className="storage-error" role="alert">{storageError}</div>}
 <div className="conversation" role="log" aria-label={`${bot.name} conversation`}><div className="conversation-inner">{!messages.length?<div className="welcome"><div className="welcome-art"><span className="orbit-ring ring-one"/><span className="orbit-ring ring-two"/><span className="little-star star-one">+</span><span className="little-star star-two">+</span><span className="orbit-dot"/><Avatar {...bot} size={124}/></div><h2>{bot.id==='coordinator'?'Welcome to your orbit.':`Meet ${bot.name||'your bot'}.`}</h2><button className="text-button" onClick={()=>{setSettings(true);}}>Make this bot your own <ChevronRight size={14}/></button></div>:<><div className="conversation-date">{!deterministic&&new Date(messages[0].createdAt).toLocaleDateString(undefined,{month:'long',day:'numeric',year:'numeric'})}</div>{messages.map(message=><article key={message.id} className={`message ${message.role}`}>{message.role==='assistant'&&!message.story?.direct_specialist&&<Avatar {...bot} size={32}/>}<div><div className="message-bubble" hidden={message.story?.direct_specialist}>{message.role==='assistant'&&<div className="bot-identity" style={{color:bot.color}}>@ {bot.name}</div>}{message.role==='assistant'?(!message.story?.direct_specialist&&<StreamingText id={message.id} text={message.content.replaceAll('Orbit Coordinator','Coordinator').replaceAll('Schedule Planner','Planner').replaceAll('Research Assistant','Researcher')} onComplete={()=>setRevealed(r=>r[message.id]?r:{...r,[message.id]:true})}/>):message.content}{message.attachments?.map(a=><details className="message-attachment" key={a.id}><summary>{a.name} · {(a.size/1024).toFixed(1)} KB</summary><p>{a.processing}{a.preview_truncated?' · Preview limited to 20,000 characters':''}</p>{a.text_preview&&<pre>{a.text_preview}</pre>}</details>)}</div>{!deterministic&&message.role==='user'&&<ApprovalPanel inline messageId={message.id}/>}{message.story&&<div className="inline-story"><ProgressiveHandoffs story={message.story} bots={workspace.bots} messageId={message.id} ready={!!revealed[message.id]||!!message.story.direct_specialist}/><small className="memory-indicator">Memory updated{message.story.domain_added?.length?` · ${message.story.domain_added.length} new plan items`:''}</small>{message.story.decision_id&&<details className="inline-evidence"><summary>Evidence behind this plan</summary><p>Based on your reported schedule and connected arrangements. User reports have not been independently provider-verified.</p>{message.story.evidence_relationships?.map(e=><p key={e.id}>{e.source} {e.relationship.toLowerCase().replaceAll('_',' ')} {e.target}.</p>)}{message.story.previous?.length>0&&<p>Earlier decisions and outcomes retrieved from FalkorDB: {message.story.previous.map(p=>p.name).join(', ')}</p>}<button className="text-button" onClick={()=>{setGraphRoot(message.story.decision_id);setGraphMode('simple');}}>Inspect recorded evidence</button></details>}</div>}<div className="message-meta">{message.role==='user'?'You':message.story?.direct_specialist?displayName(message.story.handoffs[0].name):bot.name}<span>·</span><time dateTime={new Date(message.createdAt).toISOString()}>{new Date(message.createdAt).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</time></div></div></article>)}<div className="connection-note"><span>{chatError}</span>{busy&&<span className="activity-dots" aria-label="Updating your plan"><i/><i/><i/></span>}</div></>}<div ref={end}/></div></div>
 <div className={`composer-area ${capturing?'recording':''}`}><form className="composer" onSubmit={e=>{e.preventDefault();send();}}>
 <ComposerTools draft={draft} setDraft={text=>setDrafts(d=>({...d,[bot.id]:text}))} setSource={setSource} files={files} setFiles={setFiles} busy={busy||capturing}/>
 <textarea ref={composer} readOnly={capturing} rows={1} aria-label="Message" placeholder={`Message ${bot.name||'Coordinator'}...`} value={draft} maxLength={20000} onChange={e=>{setDrafts(d=>({...d,[bot.id]:e.target.value}));e.target.style.height='auto';e.target.style.height=Math.min(144,e.target.scrollHeight)+'px';}} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send();}}}/>
 <select className="response-depth" aria-label="Response depth" title={deterministic?'Demo uses the approved story responses at every level.':'Response detail preference, not provider reasoning budget.'} value={depth} onChange={e=>{setDepth(e.target.value);localStorage.setItem('orbit.response.depth',e.target.value);}}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
 <VoiceInput key={bot.id+':'+(conversationIds.current[bot.id]||'')} draft={draft} setDraft={text=>{setDrafts(d=>({...d,[bot.id]:text}));setSource('voice_transcript');}} onActive={setCapturing} onSubmit={send} busy={busy}/>
 <button className="send-button" aria-label="Send message" disabled={(!draft.trim()&&!files.length)||busy||capturing}><ArrowUp size={19}/></button>
 </form></div></main>
  {graphMode&&<aside className="graph-dock"><ResizeHandle side="right" value={graphWidth} onChange={resizeGraph}/><Suspense fallback={<div className="graph-loading-shell" role="status">Opening graph workspace…</div>}><GraphWorkspace docked conversationId={conversationIds.current[bot.id]||''} initialMode={graphMode} initialRoot={graphRoot} rememberRoot={setGraphRoot} close={()=>setGraphMode(null)}/></Suspense></aside>}</div>
 {settings&&<Settings key={bot.id} bot={bot} update={updateBot} close={()=>setSettings(false)} persist={persist}/>}
 {creating&&<CreateBot close={()=>setCreating(false)} create={data=>{const id=crypto.randomUUID();setWorkspace(w=>({...w,bots:[...w.bots,{...data,id}],selectedId:id}));setQuery('');setCreating(false);setSidebar(false);}}/>}
 {clearing&&<Modal title="Start a fresh conversation?" close={()=>setClearing(false)}><p className="muted">Start a new conversation with {bot.name}. Previous messages and shared graph memory remain saved.</p><div className="modal-actions"><button className="secondary" onClick={()=>setClearing(false)}>Keep conversation</button><button className="primary" onClick={()=>{conversationIds.current[bot.id]='chat:'+crypto.randomUUID();delete pending.current[bot.id];setWorkspace(w=>({...w,conversations:{...w.conversations,[bot.id]:[]}}));setClearing(false);}}>Clear messages</button></div></Modal>}
 </div>;
}
createRoot(document.getElementById('root')).render(<WelcomeGate><StoryRouter Normal={App}/></WelcomeGate>);

