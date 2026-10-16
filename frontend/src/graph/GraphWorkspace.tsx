import React from 'react';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Network,GitFork,X,RefreshCw,Search,ChevronRight,Database,Unplug,LoaderCircle,Maximize2} from 'lucide-react';
import GraphCanvas from './GraphCanvas';
import Inspector from './Inspector';
import {graphService} from './service';
import {ENTITY_TYPES,TYPE_COLORS,nodeLabel,type GraphData,type GraphNode,type ViewMode,type Selection} from './models';
import './graph.css';
interface Props {initialMode:ViewMode;initialRoot:string;rememberRoot:(id:string)=>void;close:()=>void;}
export default function GraphWorkspace({initialMode,initialRoot,rememberRoot,close}:Props) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [mode,setMode]=useState(initialMode),[root,setRoot]=useState(initialRoot),[hops,setHops]=useState(2);
  const [query,setQuery]=useState(''),[filter,setFilter]=useState(''),[revision,setRevision]=useState(0),[offset,setOffset]=useState(0);
  const [entities,setEntities]=useState<GraphNode[]>([]),[next,setNext]=useState<number|null>(null),[searching,setSearching]=useState(true),[searchError,setSearchError]=useState('');
  const [graph,setGraph]=useState<GraphData|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const [selection,setSelection]=useState<Selection>(null),[collapsed,setCollapsed]=useState<Set<string>>(new Set());
  const [loadedAt,setLoadedAt]=useState<Date|null>(null);
  const focus=useCallback((id:string)=>{setRoot(id);rememberRoot(id);setSelection({kind:'node',id});setCollapsed(new Set());},[rememberRoot]);
  const toggle=useCallback((id:string)=>setCollapsed(previous=>{const next=new Set(previous);next.has(id)?next.delete(id):next.add(id);return next;}),[]);
  const refresh=useCallback(()=>{setRevision(v=>v+1);setOffset(0);},[]);
  useEffect(()=>{const prior=document.activeElement as HTMLElement;dialog.current?.showModal();const invalidate=()=>refresh();window.addEventListener('orbit:graph-changed',invalidate);return()=>{window.removeEventListener('orbit:graph-changed',invalidate);prior?.focus();};},[refresh]);
  useEffect(()=>{
    const controller=new AbortController();setSearching(true);setSearchError('');if(offset===0)setEntities([]);
    const timer=setTimeout(()=>{
      graphService.search(query,filter,offset,controller.signal).then(page=>{
        if(controller.signal.aborted)return;
        setEntities(old=>offset===0?page.items:[...old,...page.items]);setNext(page.next_offset);
        // Choose only from actual API records; no default fixture IDs.
        if(!root&&page.items[0])focus(page.items[0].id);
      }).catch(e=>{if(!controller.signal.aborted)setSearchError(e.message);}).finally(()=>{if(!controller.signal.aborted)setSearching(false);});
    },200);
    return()=>{clearTimeout(timer);controller.abort();};
    // Root changes do not require reloading the entity directory.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[query,filter,offset,revision]);
  useEffect(()=>{
    if(!root)return;
    const controller=new AbortController();setLoading(true);setGraph(null);setError('');setCollapsed(new Set());
    graphService.subgraph(root,hops,controller.signal).then(data=>{
      if(controller.signal.aborted)return;
      setGraph(data);setLoadedAt(new Date());setSelection({kind:'node',id:root});
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[root,hops,revision]);
  const focusNode=graph?.nodes.find(n=>n.id===root);
  return <dialog ref={dialog} className="graph-dialog" aria-label="Graph exploration workspace" onCancel={e=>{e.preventDefault();e.stopPropagation();close();}} onKeyDown={e=>{if(e.key==='Escape')e.stopPropagation();}}>
    <div className="graph-workspace"><header className="graph-workspace-header"><div className="graph-brand"><Network size={23}/><div><h2>Connected context<span>.</span></h2><p>Your knowledge, a little more connected.</p></div></div>
      <div className="view-switch" role="group" aria-label="Visualization mode"><button aria-pressed={mode==='network'} onClick={()=>setMode('network')}><Network size={16}/> Graph View</button><button aria-pressed={mode==='simple'} onClick={()=>setMode('simple')}><GitFork size={16}/> Simple View</button></div>
      <button className="graph-refresh" onClick={refresh} aria-label="Refresh graph"><RefreshCw size={15} className={loading?'spinning':''}/> Refresh</button><button className="icon-button" onClick={close} aria-label="Close graph workspace"><X size={21}/></button></header>
    <div className="graph-toolbar"><span className="graph-breadcrumb"><Database size={14}/> FalkorDB <ChevronRight size={13}/><strong title={focusNode?nodeLabel(focusNode):root}>{focusNode?nodeLabel(focusNode):'Choose an entity'}</strong></span><div className="depth-control"><span>Connection depth</span>{[1,2,3,4].map(depth=><button key={depth} aria-label={`${depth} ${depth===1?'hop':'hops'}`} aria-pressed={hops===depth} onClick={()=>setHops(depth)}>{depth}</button>)}</div><label className="graph-type-filter">Show <select aria-label="Filter entity type" value={filter} onChange={e=>{setFilter(e.target.value);setOffset(0);}}><option value="">All entity types</option>{ENTITY_TYPES.map(t=><option key={t}>{t}</option>)}</select></label></div>
    <div className="graph-workspace-body"><aside className="entity-directory"><div className="directory-title"><span>EXPLORE YOUR GRAPH</span><Search size={14}/></div><div className="entity-search"><Search size={15}/><input autoFocus aria-label="Search graph entities" placeholder="Find an entity or topic…" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/></div><div className="entity-results" aria-label="Graph entities">
      {searching&&<p className="directory-message" role="status">Finding entities…</p>}{searchError&&<p className="directory-message error" role="alert">{searchError}</p>}
      {!searching&&!searchError&&entities.length===0&&<p className="directory-message">{query||filter?'No matching entities. Try another search or type.':'This graph is empty. Add entities through the backend to begin.'}</p>}
      {entities.map(n=><button key={n.id} className={`entity-result ${root===n.id?'active':''}`} onClick={()=>focus(n.id)} aria-label={`Explore ${nodeLabel(n)}`}><span className="entity-result-dot" style={{background:TYPE_COLORS[n.type]}}/><span><strong>{nodeLabel(n)}</strong><small>{n.type}</small></span><ChevronRight size={13}/></button>)}
      {next!==null&&!searching&&!searchError&&<button className="load-entities" onClick={()=>setOffset(next)}>Load more entities</button>}</div>
      <div className="directory-note"><Database size={16}/><p>Read directly from FalkorDB.<br/>No inferred or generated facts.</p></div></aside>
      <section className="graph-stage" aria-label={mode==='network'?'Graph View canvas':'Simple View canvas'}>
        <div className="stage-heading"><div><span className="eyebrow">{mode==='network'?'THE CONNECTED PICTURE':'ONE CONNECTION AT A TIME'}</span><h3>{mode==='network'?'See how it all connects.':'Follow the branches.'}</h3></div>{graph&&<span className="graph-count" data-testid="graph-totals">{graph.nodes.length} entities <span>·</span> {graph.edges.length} relationships</span>}</div>
        {graph?.truncated&&<div className="graph-notice">Showing a bounded selection of paths. Reduce the depth or focus on a closer entity to explore more precisely.</div>}
        {filter&&<div className="graph-notice">Showing {filter} entities and the focus. Relationships with hidden endpoints are hidden, never rerouted.</div>}
        {mode==='simple'&&graph&&<div className="simple-key"><span>── stored relationship</span><span>┄ cross-link / shared connection</span>{collapsed.size>0&&<button onClick={()=>setCollapsed(new Set())}>Expand all branches</button>}</div>}
        {loading?<div className="graph-state" role="status"><LoaderCircle className="spinning" size={30}/><h3>Following the connections…</h3><p>Retrieving up to {hops} hops from FalkorDB.</p></div>:error?<div className="graph-state" role="alert"><Unplug size={34}/><h3>Connection interrupted.</h3><p>{error}</p><button className="secondary" onClick={refresh}>Try again</button></div>:graph?<GraphCanvas graph={graph} root={root} mode={mode} filter={filter} selection={selection} select={setSelection} collapsed={collapsed} toggle={toggle}/>:<div className="graph-state"><Network size={36}/><h3>{searchError?'Connect your graph.':'Start with something you know.'}</h3><p>{searchError||'Choose an entity from the list to explore its actual relationships.'}</p>{searchError&&<button className="secondary" onClick={refresh}>Try again</button>}</div>}
        <footer className="graph-stage-footer"><span>{graph?<><span className="graph-live-dot"/> Snapshot from FalkorDB{loadedAt?` · loaded ${loadedAt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`:''}</>:'No graph snapshot loaded'}</span><span><Maximize2 size={12}/> Select to inspect · Fit to reframe</span></footer>
      </section>{graph?<Inspector graph={graph} selection={selection} focus={focus} select={setSelection}/>:<aside className="graph-inspector"><div className="inspector-heading">INSPECTOR</div><p className="inspector-help">Entity details appear after a graph is loaded.</p></aside>}
    </div></div></dialog>;
}
