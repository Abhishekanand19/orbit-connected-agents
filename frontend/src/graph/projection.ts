import type {GraphData} from './models';
// Visibility only. Every displayed node and edge retains its persisted identity.
export function planProjection(graph:GraphData,scope='plan'):GraphData {
 if(scope==='all')return graph;
 const decisions=graph.nodes.filter(n=>n.type==='Decision'&&n.properties.record_kind==='STORY_DECISION').sort((a,b)=>b.created_at-a.created_at);
 const latest=decisions[0]?.id;
 const nodes=graph.nodes.filter(n=>{
  if(scope==='people')return n.type==='Person';
  if(scope==='evidence')return ['Claim','Source','Decision','Event'].includes(n.type)&&!['AGENT_FINDING'].includes(String(n.properties.record_kind))&&n.properties.status!=='SUPERSEDED';
  if(n.type==='Decision')return n.id===latest;
  if(n.type==='Claim')return n.properties.slot==='rumor'&&n.properties.status!=='SUPERSEDED';
  return n.properties.record_kind==='STORY_HOSPITAL'||['Person','Event','Booking','Action','Outcome'].includes(n.type)||n.type==='Task'&&(!n.properties.record_kind||n.properties.record_kind==='STORY_CHECKLIST');
 });
 const ids=new Set(nodes.map(n=>n.id));
 return {...graph,nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)),paths:[]};
}

export function withinHops(graph:GraphData,root:string,hops:number):GraphData{
 if(!graph.nodes.length)return graph;
 const start=graph.nodes.some(n=>n.id===root)?root:graph.nodes[0].id;
 const reached=new Set([start]);let frontier=[start];
 for(let depth=0;depth<hops;depth++){const next:string[]=[];for(const id of frontier)for(const e of graph.edges){const other=e.source===id?e.target:e.target===id?e.source:null;if(other&&!reached.has(other)){reached.add(other);next.push(other);}}frontier=next;}
 return {...graph,nodes:graph.nodes.filter(n=>reached.has(n.id)),edges:graph.edges.filter(e=>reached.has(e.source)&&reached.has(e.target)),paths:[]};
}
