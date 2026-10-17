import React from 'react';
import {ArrowDown,CheckCircle,Users,CalendarDays,Route,GitBranch} from 'lucide-react';
import {nodeLabel,relationLabel,type GraphData,type GraphNode,type Selection} from './models';

// The arrows indicate reading order between evidence sections, not synthetic
// database edges. Each statement below names its real supporting relationship.
export default function SimpleExplanation({graph,select}:{graph:GraphData;select:(s:Selection)=>void}){
 const byId=new Map(graph.nodes.map(n=>[n.id,n]));
 const event=graph.nodes.find(n=>n.type==='Event');
 const decisions=graph.nodes.filter(n=>n.type==='Decision'&&n.properties.record_kind==='STORY_DECISION').sort((a,b)=>b.created_at-a.created_at);
 const decision=decisions[0];
 let analysis:any={};try{analysis=JSON.parse(String(decision?.properties.analysis||'{}'));}catch{}
 const time=(n:GraphNode)=>n.properties.starts_at?new Date(String(n.properties.starts_at)).toLocaleTimeString('en-IN',{hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'}):'';
 const fact=(n:GraphNode)=> <button className="flow-fact" key={n.id} data-entity-id={n.id} onClick={()=>select({kind:'node',id:n.id})}>{nodeLabel(n)}{!!n.properties.starts_at&&<strong>{time(n)}{n.properties.location?` · ${n.properties.location}`:''}</strong>}</button>;
 const relation=(id:string)=>{const e=graph.edges.find(e=>e.id===id);return e?<button className="flow-relation" key={id} data-edge-id={id} onClick={()=>select({kind:'edge',id})}>{byId.get(e.source)?nodeLabel(byId.get(e.source)!):e.source} <span>{relationLabel(e.type)}</span> {byId.get(e.target)?nodeLabel(byId.get(e.target)!):e.target}</button>:null;};
 const stages:{title:string;icon:typeof Users;content:React.ReactNode;kind:string}[]=[];
 if(!event){
  const family=graph.edges.filter(e=>['PARENT_OF','SIBLING_OF'].includes(e.type));
  if(family.length){
   const people=graph.nodes.filter(n=>n.type==='Person');
   const ordered=[...people].sort((a,b)=>{const incoming=(id:string)=>family.filter(e=>e.target===id).length;return incoming(a.id)-incoming(b.id);});
   for(const n of ordered)stages.push({title:String(n.properties.name||'Family connection'),icon:Users,kind:'people',content:<>{fact(n)}{family.filter(e=>e.source===n.id).map(e=>relation(e.id))}</>});
  }else stages.push({title:'Recorded context',icon:Users,kind:'people',content:<>{graph.nodes.slice(0,6).map(fact)}{graph.edges.slice(0,5).map(e=>relation(e.id))}</>});
 }else{
  stages.push({title:event.properties.location==='video'?'A video visit is now reported':'The current appointment',icon:CalendarDays,kind:'update',content:<>{fact(event)}<small>Reported by you · not independently provider-verified</small></>});
  const paths=analysis.affected||[];
  const edgeIds=[...new Set<string>(paths.flatMap((p:any)=>p.edge_ids))].filter(id=>graph.edges.some(e=>e.id===id));
  const deps=edgeIds.length?edgeIds:graph.edges.filter(e=>e.type==='DEPENDS_ON'&&e.target===event.id).map(e=>e.id);
  if(deps.length)stages.push({title:'What this affects',icon:Route,kind:'impact',content:<>{deps.slice(0,3).map(relation)}</>});
  const available=graph.edges.filter(e=>e.type==='AVAILABLE_FOR'&&e.target===event.id);
  const assignments=graph.edges.filter(e=>e.type==='ASSIGNED_TO');
  if(!available.length&&assignments.length)stages.push({title:'Responsibilities',icon:Users,kind:'people',content:<>{assignments.slice(0,3).map(e=>relation(e.id))}</>});
  if(available.length)stages.push({title:'Who can help',icon:Users,kind:'people',content:available.map(e=>{const n=byId.get(e.source);return n?<div key={e.id}>{fact(n)}<small>{n.properties.escort==='CONFIRMED'?'Agreed to accompany':n.properties.availability==='REFUTED'?'Unavailable':'Availability reported; agreement still needed'}{n.properties.available_from?` · from ${n.properties.available_from}`:''}{n.properties.unavailable_from?` · unavailable after ${n.properties.unavailable_from}`:''}</small></div>:null;})});
  if(decision)stages.push({title:'The decision',icon:GitBranch,kind:'decision',content:<button className="flow-fact" data-entity-id={decision.id} onClick={()=>select({kind:'node',id:decision.id})}>{String(analysis.reason||nodeLabel(decision)).replace(/^WAIT\s*—\s*/,'')}</button>});
  const actions=graph.nodes.filter(n=>n.type==='Action');
  if(actions.length)stages.push({title:'Actions and results',icon:CheckCircle,kind:'action',content:actions.map(n=><div key={n.id}>{fact(n)}{graph.edges.filter(e=>e.source===n.id&&e.type==='PRODUCED').map(e=><div key={e.id}>{relation(e.id)}<small>Recorded execution outcome; select to inspect readback.</small></div>)}</div>)});
 }
 return <div className="simple-explanation" data-testid="simple-explanation"><div className="flow-caption">YOUR PLAN, EXPLAINED <span>Evidence in reading order</span></div>{stages.map((step,i)=><React.Fragment key={step.title}>{i>0&&<ArrowDown className="flow-arrow" aria-hidden/>}<section className={`explanation-step ${step.kind}`}><h3><step.icon size={19}/>{step.title}</h3>{step.content}</section></React.Fragment>)}<p className="flow-footnote">Same FalkorDB snapshot. Arrows between sections show reading order; relationship statements retain their stored direction.</p></div>;
}
