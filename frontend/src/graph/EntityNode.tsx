import React from 'react';
import {memo} from 'react';
import {Handle,Position,useStore,type Node,type NodeProps} from '@xyflow/react';
import {ChevronDown,ChevronRight,UserRound,CalendarDays,CheckSquare,Ticket,MessageSquare,Bot,FileText,Quote,GitBranch,Zap,CheckCircle,MessagesSquare} from 'lucide-react';
import {TYPE_COLORS,nodeLabel,type GraphNode,type ViewMode} from './models';
const icons={Person:UserRound,Event:CalendarDays,Task:CheckSquare,Booking:Ticket,Conversation:MessagesSquare,Message:MessageSquare,Bot,Source:FileText,Claim:Quote,Decision:GitBranch,Action:Zap,Outcome:CheckCircle};
export type EntityFlowNode=Node<{entity:GraphNode;mode:ViewMode;root:boolean;childCount:number;collapsed:boolean;toggle:()=>void;highlight:boolean;fresh?:boolean;compact?:boolean},'entity'>;
export const EntityNode=memo(function EntityNode({data,selected}:NodeProps<EntityFlowNode>) {
  const zoom=useStore(state=>state.transform[2]);
  const Icon=icons[data.entity.type], label=nodeLabel(data.entity);
  return <div className={`entity-node ${data.mode} ${data.compact?'compact':''} ${selected?'is-selected':''} ${data.root?'is-root':''} ${data.highlight?'on-path':''} ${data.fresh?'recently-changed':''} ${data.entity.properties.status==='SUPERSEDED'?'superseded':''}`} style={{'--entity-color':data.entity.type==='Action'&&data.entity.properties.status!=='VERIFIED'?'#f4c67b':TYPE_COLORS[data.entity.type],'--label-scale':Math.min(1.7,1/zoom)} as React.CSSProperties} title={`${label}\n${data.entity.type} · ${data.entity.id}`} data-entity-id={data.entity.id}>
    {Object.entries({top:Position.Top,bottom:Position.Bottom,left:Position.Left,right:Position.Right}).flatMap(([key,position])=>[
      <Handle key={'s'+key} id={'s-'+key} type="source" position={position} isConnectable={false}/>,
      <Handle key={'t'+key} id={'t-'+key} type="target" position={position} isConnectable={false}/>
    ])}
    <span className="entity-glyph"><Icon size={data.mode==='simple'?19:24} strokeWidth={1.6}/></span>
    <div className="entity-copy"><span className="entity-type">{data.entity.type}{data.root?' · FOCUS':''}</span><strong>{label}</strong>{!!data.entity.properties.starts_at&&<span className="node-time">{new Date(String(data.entity.properties.starts_at)).toLocaleTimeString('en-IN',{hour:'numeric',minute:'2-digit',timeZone:'Asia/Kolkata'})}</span>}</div>
    {data.mode==='simple'&&data.childCount>0&&<button className="branch-toggle nodrag nopan" aria-label={`${data.collapsed?'Expand':'Collapse'} ${label}`} onClick={e=>{e.stopPropagation();data.toggle();}}>{data.collapsed?<ChevronRight size={14}/>:<ChevronDown size={14}/>}<span>{data.childCount}</span></button>}
  </div>;
});
