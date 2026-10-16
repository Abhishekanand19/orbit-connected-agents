import React from 'react';
import {BaseEdge,EdgeLabelRenderer,getBezierPath,useStore,type Edge,type EdgeProps} from '@xyflow/react';
import type {GraphEdge} from './models';
export type RelationshipFlowEdge=Edge<{entity:GraphEdge;label:string;cross:boolean;slot:number;labelOffset:{x:number;y:number};inspect:()=>void;active:boolean},'relationship'>;
export function RelationshipEdge(props:EdgeProps<RelationshipFlowEdge>) {
  const zoom=useStore(state=>state.transform[2]);
  const {data,sourceX:sx,sourceY:sy,targetX:tx,targetY:ty}=props;
  if(!data) return null;
  let [path,x,y]=getBezierPath({...props,curvature:.3});
  if(data.entity.source===data.entity.target) {
    path=`M ${sx} ${sy} C ${sx+130} ${sy-100}, ${tx+130} ${ty+100}, ${tx} ${ty}`;x=sx+100;y=sy;
  } else if(data.cross) {
    const bend=Math.max(sx,tx)+65+(data.slot%4)*35;
    path=`M ${sx} ${sy} C ${bend} ${sy}, ${bend} ${ty}, ${tx} ${ty}`;
    x=(sx+tx+6*bend)/8;y=(sy+ty)/2;
  }
  return <><BaseEdge path={path} markerEnd={props.markerEnd} interactionWidth={24} style={{stroke:data.active?'#efb39a':data.cross?'#81758f':'#686b6d',strokeWidth:data.active?2.5:1.5,strokeDasharray:data.cross?'6 5':undefined}}/>
    {!data.cross&&(data.labelOffset.x!==0||data.labelOffset.y!==0)&&<path d={`M ${x} ${y} L ${x+data.labelOffset.x} ${y+data.labelOffset.y}`} stroke="#555e62" strokeDasharray="2 3" fill="none" style={{pointerEvents:'none'}}/>}
    {!data.cross&&<EdgeLabelRenderer><button className={`relationship-label nodrag nopan ${data.active?'on-path':''} ${data.cross?'cross-link':''}`} style={{transform:`translate(-50%, -50%) translate(${x+data.labelOffset.x}px,${y+data.labelOffset.y}px) scale(${Math.min(1.8,1/zoom)})`}} onClick={data.inspect} title={`${data.entity.type} · ${data.entity.source} → ${data.entity.target}`} aria-label={`Inspect relationship ${data.entity.type} from ${data.entity.source} to ${data.entity.target}`} data-edge-id={data.entity.id}>{data.label}{data.cross&&<span> ↗</span>}</button></EdgeLabelRenderer>}</>;
}
