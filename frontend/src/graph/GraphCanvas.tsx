import React from 'react';
import {useEffect,useMemo,useState,useRef} from 'react';
import {ReactFlow,Background,Controls,MarkerType,getBezierPath,Position,useNodesState,type ReactFlowInstance} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {EntityNode,type EntityFlowNode} from './EntityNode';
import {RelationshipEdge,type RelationshipFlowEdge} from './RelationshipEdge';
import {layoutGraph,connectedPath} from './layout';
import {nodeLabel,relationLabel,type GraphData,type Selection,type ViewMode} from './models';
const nodeTypes={entity:EntityNode},edgeTypes={relationship:RelationshipEdge};
interface Props {graph:GraphData;root:string;mode:ViewMode;filter:string;selection:Selection;select:(s:Selection)=>void;collapsed:Set<string>;toggle:(id:string)=>void;compact?:boolean;}
export default function GraphCanvas({graph,root,mode,filter,selection,select,collapsed,toggle,compact=false}:Props) {
  const fitted=useRef(false),canvas=useRef<HTMLDivElement>(null);
  const previous=useRef(new Map<string,string>());
  const coordinates=useRef(new Map<string,{x:number;y:number}>());
  const layout=useMemo(()=>{const next=layoutGraph(graph,root,mode,filter,collapsed,compact,coordinates.current);for(const [id,p] of next.positions)coordinates.current.set(id,p);return next;},[graph,root,mode,filter,collapsed,compact]);
  const [nodes,setNodes,onNodesChange]=useNodesState<EntityFlowNode>([]);
  const [instance,setInstance]=useState<ReactFlowInstance<EntityFlowNode,RelationshipFlowEdge>|null>(null);
  const highlighted=useMemo(()=>{
    const decisions=graph.nodes.filter(n=>n.type==='Decision'&&n.properties.record_kind==='STORY_DECISION').sort((a,b)=>b.created_at-a.created_at);
    const decision=decisions.find(n=>n.id===root||n.id===selection?.id)||decisions[0];
    if(decision){try{const analysis=JSON.parse(String(decision.properties.analysis));return new Set<string>(analysis.affected.flatMap((p:{edge_ids:string[]})=>p.edge_ids));}catch{/* Fall back for older receipts. */}}
    return selection?.kind==='node'?connectedPath(layout,root,selection.id):new Set<string>();
  },[graph,layout,selection,root]);
  useEffect(()=>{
    setNodes(layout.nodes.map(n=>({id:n.id,type:'entity',position:layout.positions.get(n.id)!,ariaLabel:`Inspect ${nodeLabel(n)}`,
      data:{entity:n,mode,compact,root:n.id===root,childCount:layout.tree.children.get(n.id)?.length||0,collapsed:collapsed.has(n.id),toggle:()=>toggle(n.id),highlight:false,fresh:previous.current.get(n.id)!==JSON.stringify(n.properties)}})));
    previous.current=new Map(layout.nodes.map(n=>[n.id,JSON.stringify(n.properties)]));
  },[layout,mode,root,collapsed,toggle,setNodes]);
  useEffect(()=>{if(!instance||fitted.current||!layout.nodes.length) return;fitted.current=true;const frame=requestAnimationFrame(()=>instance.fitView({padding:.08,maxZoom:1.15,minZoom:.42,duration:250}));return()=>cancelAnimationFrame(frame);},[instance,layout]);
  // Resize the viewport, not the graph: keep nodes and evidence positions intact.
  useEffect(()=>{
    if(!instance||!canvas.current)return;
    let size='',frame=0;
    const observer=new ResizeObserver(([entry])=>{
      const next=`${Math.round(entry.contentRect.width)}:${Math.round(entry.contentRect.height)}`;
      if(size&&size!==next&&fitted.current){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{void instance.fitView({padding:.08,maxZoom:1.15,minZoom:.2,duration:0});});}
      size=next;
    });
    observer.observe(canvas.current);
    return()=>{observer.disconnect();cancelAnimationFrame(frame);};
  },[instance]);
  const painted=nodes.map(n=>({...n,selected:selection?.kind==='node'&&selection.id===n.id,data:{...n.data,highlight:layout.edges.some(e=>highlighted.has(e.id)&&(e.source===n.id||e.target===n.id))}}));
  const nodePositions=new Map(nodes.map(n=>[n.id,n.position]));
  const labelBoxes:{x:number;y:number;width:number;height:number}[]=[];
  const nodeBoxes=nodes.map(n=>({x:n.position.x+layout.width/2,y:n.position.y+layout.height/2,width:layout.width+18,height:layout.height+18}));
  const overlaps=(a:{x:number;y:number;width:number;height:number},b:typeof a)=>Math.abs(a.x-b.x)<(a.width+b.width)/2&&Math.abs(a.y-b.y)<(a.height+b.height)/2;
  const edges:RelationshipFlowEdge[]=layout.edges.map((edge,i)=>{
    const source=nodePositions.get(edge.source)||layout.positions.get(edge.source)!, target=nodePositions.get(edge.target)||layout.positions.get(edge.target)!;
    const cross=mode==='simple'&&!compact&&!new Set(layout.tree.parentEdge.values()).has(edge.id);
    const forward=target.y>source.y;
    const horizontal=Math.abs(source.y-target.y)<10;
    const sideways=mode==='network'&&Math.abs(target.x-source.x)>Math.abs(target.y-source.y);
    const sourceSide=sideways?(target.x>source.x?'right':'left'):cross?'right':horizontal?'top':forward?'bottom':'top';
    const targetSide=sideways?(target.x>source.x?'left':'right'):cross?'right':horizontal?'top':forward?'top':'bottom';
    const active=highlighted.has(edge.id)||(selection?.kind==='edge'&&selection.id===edge.id);
    const point=(p:{x:number;y:number},side:string)=>({x:p.x+(side==='left'?0:side==='right'?layout.width:layout.width/2),y:p.y+(side==='top'?0:side==='bottom'?layout.height:layout.height/2)});
    const sp=point(source,sourceSide),tp=point(target,targetSide);
    const positions:Record<string,Position>={top:Position.Top,bottom:Position.Bottom,left:Position.Left,right:Position.Right};
    const [,lx,ly]=getBezierPath({sourceX:sp.x,sourceY:sp.y,targetX:tp.x,targetY:tp.y,sourcePosition:positions[sourceSide],targetPosition:positions[targetSide],curvature:.3});
    const anchor={x:Math.abs(sp.y-tp.y)<2?(sp.x+tp.x)/2:lx,y:Math.abs(sp.y-tp.y)<2?sp.y-(45+(i%3)*22)*.75:ly};
    let labelOffset={x:0,y:0};
    if(mode==='network'&&edge.source!==edge.target){
      const width=Math.max(90,edge.type.length*8+15),height=28;
      const candidates=[0,-45,45,-90,90,-135,135,-180,180].flatMap(y=>[0,-80,80,-160,160,-240,240].map(x=>({x,y})));
      labelOffset=candidates.find(o=>!labelBoxes.concat(nodeBoxes).some(b=>overlaps({x:anchor.x+o.x,y:anchor.y+o.y,width,height},b)))||{x:0,y:(i%3-1)*40};
      labelBoxes.push({x:anchor.x+labelOffset.x,y:anchor.y+labelOffset.y,width,height});
    }
    return {id:edge.id,source:edge.source,target:edge.target,type:'relationship',sourceHandle:'s-'+sourceSide,targetHandle:'t-'+targetSide,
      markerEnd:{type:MarkerType.ArrowClosed,width:18,height:18,color:active?'#314ca5':'#8bab8c'},
      data:{entity:edge,labelOffset,label:mode==='simple'?relationLabel(edge.type):edge.type,cross,slot:i,inspect:()=>select({kind:'edge',id:edge.id}),active}};
  });
  return <div ref={canvas} className="graph-canvas" data-testid="graph-canvas" data-mode={mode} data-node-count={nodes.length} data-edge-count={edges.length}>
    <ReactFlow<EntityFlowNode,RelationshipFlowEdge> nodes={painted} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      onInit={setInstance} onNodesChange={onNodesChange} onNodeDragStop={(_,n)=>coordinates.current.set(n.id,{...n.position})} onNodeClick={(_,n)=>select({kind:'node',id:n.id})}
      onEdgeClick={(_,e)=>select({kind:'edge',id:e.id})} onPaneClick={()=>select(null)}
      nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={.2} maxZoom={2.2}
      colorMode="light" onlyRenderVisibleElements={false}>
      <Background color="#d8e0e6" gap={28} size={.7}/><Controls showInteractive={false} fitViewOptions={{padding:.08,maxZoom:1.15}}/>
    </ReactFlow>
    {mode==='simple'&&edges.some(e=>e.data?.cross)&&<div className="simple-crosslinks" aria-label="Cross-links and shared connections"><span>SHARED CONNECTIONS</span><div>{edges.filter(e=>e.data?.cross).map(e=><button key={e.id} className="cross-link" data-edge-id={e.id} onClick={()=>select({kind:'edge',id:e.id})} title={`${e.data!.entity.type}: ${e.source} → ${e.target}`}><strong>{nodeLabel(graph.nodes.find(n=>n.id===e.source)!)}</strong><small>{relationLabel(e.data!.entity.type)} →</small><strong>{nodeLabel(graph.nodes.find(n=>n.id===e.target)!)}</strong></button>)}</div></div>}
    <div className="canvas-guide">{mode==='simple'?'Branches organize the view. Arrows preserve stored direction.':'Drag nodes to arrange · Drag the canvas to pan · Scroll to zoom'}</div>
    {(nodes.length<graph.nodes.length||edges.length<graph.edges.length)&&<div className="hidden-count">{graph.nodes.length-nodes.length} entities · {graph.edges.length-edges.length} relationships hidden by filters or collapsed branches</div>}
  </div>;
}
