import dagre from '@dagrejs/dagre';
import type {GraphData,GraphEdge,ViewMode} from './models';

// An undirected BFS chooses drawing branches only. Stored edges are never rewritten.
export function spanningTree(graph:GraphData,root:string) {
  const parent=new Map<string,string>(), parentEdge=new Map<string,string>();
  const children=new Map<string,string[]>();
  const seen=new Set<string>([root]), queue=[root];
  const priority=['PARENT_OF','SIBLING_OF','DEPENDS_ON','ASSIGNED_TO','PARTICIPATES_IN','RELATED_TO','AFFECTS','HAS_CONVERSATION','HAS_MESSAGE','MENTIONED_IN'];
  const rank=(type:string)=>{const i=priority.indexOf(type);return i<0?priority.length:i;};
  const edges=[...graph.edges].sort((a,b)=>rank(a.type)-rank(b.type)||a.type.localeCompare(b.type)||a.id.localeCompare(b.id));
  for(let index=0;index<queue.length;index++) {
    const current=queue[index];
    for(const edge of edges) {
      const neighbor=edge.source===current?edge.target:edge.target===current?edge.source:null;
      if(!neighbor || seen.has(neighbor)) continue;
      seen.add(neighbor);queue.push(neighbor);parent.set(neighbor,current);parentEdge.set(neighbor,edge.id);
      children.set(current,[...(children.get(current)||[]),neighbor]);
    }
  }
  return {parent,parentEdge,children};
}
export function visibleGraph(graph:GraphData,root:string,type:string,collapsed:Set<string>,mode:ViewMode) {
  const tree=spanningTree(graph,root), hidden=new Set<string>();
  const hide=(id:string)=>{for(const child of tree.children.get(id)||[]){hidden.add(child);hide(child);}};
  if(mode==='simple') for(const id of collapsed) hide(id);
  const nodes=graph.nodes.filter(n=>!hidden.has(n.id)&&(!type||n.type===type));
  const ids=new Set(nodes.map(n=>n.id));
  return {nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)),tree};
}
export function layoutGraph(graph:GraphData,root:string,mode:ViewMode,type:string,collapsed:Set<string>,compact=false,previous=new Map<string,{x:number;y:number}>()) {
  const visible=visibleGraph(graph,root,type,collapsed,mode);
  const arranged=mode==='simple'?visibleGraph(graph,root,'',collapsed,mode):visible;
  const width=mode==='simple'?224:124, height=mode==='simple'?94:124;
  if(mode==='network'){
    // Deterministic spring layout; only coordinates are calculated, never facts.
    const items=visible.nodes, positions=new Map<string,{x:number;y:number}>();
    items.forEach((n,i)=>{const angle=i*2.399963;const radius=150*Math.sqrt(i);positions.set(n.id,previous.has(n.id)?{...previous.get(n.id)!}:{x:Math.cos(angle)*radius,y:Math.sin(angle)*radius});});
    for(let iteration=0;iteration<240;iteration++){
      const force=new Map(items.map(n=>[n.id,{x:0,y:0}]));
      for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){
        const a=positions.get(items[i].id)!,b=positions.get(items[j].id)!;let dx=a.x-b.x,dy=a.y-b.y;const dist=Math.max(1,Math.hypot(dx,dy));
        const push=26000/(dist*dist)+(dist<195?(195-dist)*.6:0);
        const fa=force.get(items[i].id)!,fb=force.get(items[j].id)!;fa.x+=dx/dist*push;fa.y+=dy/dist*push;fb.x-=dx/dist*push;fb.y-=dy/dist*push;
      }
      for(const e of visible.edges){if(e.source===e.target)continue;const a=positions.get(e.source)!,b=positions.get(e.target)!;const dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(1,Math.hypot(dx,dy)),pull=(dist-245)*.025;const fa=force.get(e.source)!,fb=force.get(e.target)!;fa.x+=dx/dist*pull;fa.y+=dy/dist*pull;fb.x-=dx/dist*pull;fb.y-=dy/dist*pull;}
      for(const n of items){if(previous.has(n.id))continue;const p=positions.get(n.id)!,f=force.get(n.id)!;p.x+=Math.max(-12,Math.min(12,f.x-p.x*.002));p.y+=Math.max(-12,Math.min(12,f.y-p.y*.002));}
    }
    return {...visible,positions,width,height};
  }

  const layout=new dagre.graphlib.Graph({multigraph:true});
  layout.setGraph({rankdir:'TB',nodesep:mode==='simple'?80:110,ranksep:mode==='simple'?112:132,marginx:70,marginy:60});
  layout.setDefaultEdgeLabel(()=>({}));
  for(const n of arranged.nodes) layout.setNode(n.id,{width,height});
  const ids=new Set(arranged.nodes.map(n=>n.id));
  if(mode==='simple') {
    for(const [child,parent] of visible.tree.parent) {
      if(ids.has(child)&&ids.has(parent)) layout.setEdge(parent,child,{},visible.tree.parentEdge.get(child));
    }
  } else for(const e of visible.edges) if(e.source!==e.target) layout.setEdge(e.source,e.target,{},e.id);
  dagre.layout(layout);
  const positions=new Map(visible.nodes.map(n=>{const p=layout.node(n.id);return [n.id,{x:p.x-width/2,y:p.y-height/2}];}));
  return {...visible,positions,width,height};
}
export function connectedPath(graph:Pick<GraphData,'nodes'|'edges'>,root:string,target:string):Set<string> {
  const visited=new Set([root]), queue=[root], previous=new Map<string,{id:string,edge:GraphEdge}>();
  for(let i=0;i<queue.length;i++) {
    if(queue[i]===target) break;
    for(const edge of graph.edges) {
      const next=edge.source===queue[i]?edge.target:edge.target===queue[i]?edge.source:null;
      if(next&&!visited.has(next)){visited.add(next);previous.set(next,{id:queue[i],edge});queue.push(next);}
    }
  }
  const path=new Set<string>();let current=target;
  while(previous.has(current)){const prior=previous.get(current)!;path.add(prior.edge.id);current=prior.id;}
  return path;
}
