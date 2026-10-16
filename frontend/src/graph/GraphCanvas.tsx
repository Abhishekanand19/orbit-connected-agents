import React from 'react';
import {useEffect,useMemo,useState} from 'react';
import {ReactFlow,Background,Controls,MarkerType,useNodesState,type ReactFlowInstance} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {EntityNode,type EntityFlowNode} from './EntityNode';
import {RelationshipEdge,type RelationshipFlowEdge} from './RelationshipEdge';
import {layoutGraph,connectedPath} from './layout';
import {nodeLabel,relationLabel,type GraphData,type Selection,type ViewMode} from './models';
const nodeTypes={entity:EntityNode},edgeTypes={relationship:RelationshipEdge};
interface Props {graph:GraphData;root:string;mode:ViewMode;filter:string;selection:Selection;select:(s:Selection)=>void;collapsed:Set<string>;toggle:(id:string)=>void;}
export default function GraphCanvas({graph,root,mode,filter,selection,select,collapsed,toggle}:Props) {
  const layout=useMemo(()=>layoutGraph(graph,root,mode,filter,collapsed),[graph,root,mode,filter,collapsed]);
  const [nodes,setNodes,onNodesChange]=useNodesState<EntityFlowNode>([]);
  const [instance,setInstance]=useState<ReactFlowInstance<EntityFlowNode,RelationshipFlowEdge>|null>(null);
  const highlighted=useMemo(()=>selection?.kind==='node'?connectedPath(layout,root,selection.id):new Set<string>(),[layout,selection,root]);
  useEffect(()=>{
    setNodes(layout.nodes.map(n=>({id:n.id,type:'entity',position:layout.positions.get(n.id)!,ariaLabel:`Inspect ${nodeLabel(n)}`,
      data:{entity:n,mode,root:n.id===root,childCount:layout.tree.children.get(n.id)?.length||0,collapsed:collapsed.has(n.id),toggle:()=>toggle(n.id),highlight:false}})));
  },[layout,mode,root,collapsed,toggle,setNodes]);
  useEffect(()=>{if(!instance) return;const timer=setTimeout(()=>instance.fitView({padding:.18,maxZoom:1,minZoom:.25,duration:200}),100);return()=>clearTimeout(timer);},[instance,layout]);
  const painted=nodes.map(n=>({...n,selected:selection?.kind==='node'&&selection.id===n.id,data:{...n.data,highlight:layout.edges.some(e=>highlighted.has(e.id)&&(e.source===n.id||e.target===n.id))}}));
  const nodePositions=new Map(nodes.map(n=>[n.id,n.position]));
  const labelBoxes:{x:number;y:number;width:number;height:number}[]=[];
  const nodeBoxes=nodes.map(n=>({x:n.position.x+layout.width/2,y:n.position.y+layout.height/2,width:layout.width+14,height:layout.height+14}));
  const overlaps=(a:{x:number;y:number;width:number;height:number},b:typeof a)=>Math.abs(a.x-b.x)<(a.width+b.width)/2&&Math.abs(a.y-b.y)<(a.height+b.height)/2;
  const edges:RelationshipFlowEdge[]=layout.edges.map((edge,i)=>{
    const source=nodePositions.get(edge.source)||layout.positions.get(edge.source)!, target=nodePositions.get(edge.target)||layout.positions.get(edge.target)!;
    const cross=mode==='simple'&&!new Set(layout.tree.parentEdge.values()).has(edge.id);
    const forward=target.y>source.y;
    const sourceSide=cross?'right':forward?'bottom':'top';
    const targetSide=cross?'right':forward?'top':'bottom';
    const active=highlighted.has(edge.id)||(selection?.kind==='edge'&&selection.id===edge.id);
    const anchor={x:(source.x+target.x+layout.width)/2,y:(source.y+target.y+layout.height)/2};
    let labelOffset={x:0,y:0};
    if(mode==='network'&&edge.source!==edge.target){
      const width=Math.max(105,edge.type.length*9+22),height=38;
      const candidates=[0,-40,40,-80,80,-120,120].flatMap(y=>[0,-75,75,-150,150].map(x=>({x,y})));
      labelOffset=candidates.find(o=>!labelBoxes.concat(nodeBoxes).some(b=>overlaps({x:anchor.x+o.x,y:anchor.y+o.y,width,height},b)))||{x:0,y:(i%3-1)*40};
      labelBoxes.push({x:anchor.x+labelOffset.x,y:anchor.y+labelOffset.y,width,height});
    }
    return {id:edge.id,source:edge.source,target:edge.target,type:'relationship',sourceHandle:'s-'+sourceSide,targetHandle:'t-'+targetSide,
      markerEnd:{type:MarkerType.ArrowClosed,width:18,height:18,color:active?'#efb39a':'#8c8b91'},
      data:{entity:edge,labelOffset,label:mode==='simple'?relationLabel(edge.type):edge.type,cross,slot:i,inspect:()=>select({kind:'edge',id:edge.id}),active}};
  });
  return <div className="graph-canvas" data-testid="graph-canvas" data-mode={mode} data-node-count={nodes.length} data-edge-count={edges.length}>
    <ReactFlow<EntityFlowNode,RelationshipFlowEdge> nodes={painted} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      onInit={setInstance} onNodesChange={onNodesChange} onNodeClick={(_,n)=>select({kind:'node',id:n.id})}
      onEdgeClick={(_,e)=>select({kind:'edge',id:e.id})} onPaneClick={()=>select(null)}
      nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null} minZoom={.2} maxZoom={2.2}
      fitView colorMode="dark" onlyRenderVisibleElements={false}>
      <Background color="#353637" gap={28} size={1}/><Controls showInteractive={false} fitViewOptions={{padding:.18,maxZoom:1}}/>
    </ReactFlow>
    {mode==='simple'&&edges.some(e=>e.data?.cross)&&<div className="simple-crosslinks" aria-label="Cross-links and shared connections"><span>SHARED CONNECTIONS</span><div>{edges.filter(e=>e.data?.cross).map(e=><button key={e.id} className="cross-link" data-edge-id={e.id} onClick={()=>select({kind:'edge',id:e.id})} title={`${e.data!.entity.type}: ${e.source} → ${e.target}`}><strong>{nodeLabel(graph.nodes.find(n=>n.id===e.source)!)}</strong><small>{relationLabel(e.data!.entity.type)} →</small><strong>{nodeLabel(graph.nodes.find(n=>n.id===e.target)!)}</strong></button>)}</div></div>}
    <div className="canvas-guide">{mode==='simple'?'Branches organize the view. Arrows preserve stored direction.':'Drag nodes to arrange · Drag the canvas to pan · Scroll to zoom'}</div>
    {(nodes.length<graph.nodes.length||edges.length<graph.edges.length)&&<div className="hidden-count">{graph.nodes.length-nodes.length} entities · {graph.edges.length-edges.length} relationships hidden by filters or collapsed branches</div>}
  </div>;
}
