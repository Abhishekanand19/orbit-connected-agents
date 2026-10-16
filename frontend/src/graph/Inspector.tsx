import React from 'react';
import {ArrowRight,Focus,Link2,FileText} from 'lucide-react';
import {nodeLabel,relationLabel,TYPE_COLORS,type GraphData,type GraphNode,type Selection,type Properties} from './models';
function PropertiesList({properties}:{properties:Properties}) {
  return <dl className="property-list">{Object.entries(properties).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value==='object'?JSON.stringify(value):String(value)}</dd></div>)}</dl>;
}
function Timestamp({value}:{value:number}) { return <time dateTime={new Date(value).toISOString()}>{new Date(value).toLocaleString()}</time>; }
export default function Inspector({graph,selection,focus,select}:{graph:GraphData;selection:Selection;focus:(id:string)=>void;select:(s:Selection)=>void}) {
  const node=selection?.kind==='node'?graph.nodes.find(n=>n.id===selection.id):undefined;
  const edge=selection?.kind==='edge'?graph.edges.find(e=>e.id===selection.id):undefined;
  const find=(id:string)=>graph.nodes.find(n=>n.id===id)!;
  const connected=node?graph.edges.filter(e=>e.source===node.id||e.target===node.id):[];
  const sources=connected.map(e=>find(e.source===node?.id?e.target:e.source)).filter(n=>n&&['Source','Claim','Message'].includes(n.type));
  const uniqueSources=[...new Map(sources.map(n=>[n.id,n])).values()];
  function EntityLink({entity}:{entity:GraphNode}) {return <button className="inspector-entity-link" onClick={()=>select({kind:'node',id:entity.id})}><span style={{background:TYPE_COLORS[entity.type]}}/>{nodeLabel(entity)}</button>;}
  return <aside className="graph-inspector" aria-label="Graph inspector"><div className="inspector-heading"><span>INSPECTOR</span><span>Stored graph data</span></div>
    {!node&&!edge?<div className="inspector-empty"><Focus size={30}/><h3>Follow a connection.</h3><p>Select an entity or relationship to inspect what is actually stored in FalkorDB.</p></div>:node?<>
      <div className="inspector-identity"><span className="type-pill" style={{color:TYPE_COLORS[node.type]}}>{node.type}</span><h2>{nodeLabel(node)}</h2><code>{node.id}</code>{(node.properties.status||node.properties.evidence_state)?<span className="evidence-pill">{String(node.properties.status||node.properties.evidence_state)}</span>:null}</div>
      <button className="focus-entity" onClick={()=>focus(node.id)}><Focus size={16}/> Explore from here <ArrowRight size={15}/></button>
      <section><h3>Properties</h3><PropertiesList properties={node.properties}/><dl className="property-list"><div><dt>Created</dt><dd><Timestamp value={node.created_at}/></dd></div><div><dt>Updated</dt><dd><Timestamp value={node.updated_at}/></dd></div></dl></section>
      {uniqueSources.length>0&&<section><h3><FileText size={13}/> Evidence & mentions</h3>{uniqueSources.map(n=><EntityLink key={n.id} entity={n}/>)}</section>}
      <section><h3><Link2 size={13}/> Connections <span>{connected.length}</span></h3>{connected.length===0&&<p className="inspector-help">No connections in this returned subgraph.</p>}{connected.map(e=><button key={e.id} className="connection-row" onClick={()=>select({kind:'edge',id:e.id})}><span>{nodeLabel(find(e.source))}</span><small>{relationLabel(e.type)} <ArrowRight size={12}/></small><span>{nodeLabel(find(e.target))}</span></button>)}</section>
    </>:edge?<><div className="inspector-identity"><span className="type-pill">RELATIONSHIP</span><h2>{relationLabel(edge.type)}</h2><code>{edge.type}</code></div><div className="edge-direction"><EntityLink entity={find(edge.source)}/><ArrowRight size={18}/><EntityLink entity={find(edge.target)}/></div><p className="inspector-help">Arrow points from the stored source to the stored target, regardless of its position on the canvas.</p><section><h3>Stored relationship</h3><PropertiesList properties={{id:edge.id,source:edge.source,target:edge.target,...edge.properties}}/><dl className="property-list"><div><dt>Created</dt><dd><Timestamp value={edge.created_at}/></dd></div><div><dt>Updated</dt><dd><Timestamp value={edge.updated_at}/></dd></div></dl></section></>:null}
  </aside>;
}
