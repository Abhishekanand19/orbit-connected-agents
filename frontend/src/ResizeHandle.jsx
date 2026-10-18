import React,{useRef} from 'react';
export default function ResizeHandle({side,value,onChange}){
 const drag=useRef(null);
 return <div role="separator" aria-label={side==='left'?'Resize bot sidebar':'Resize graph sidebar'} aria-orientation="vertical" aria-valuenow={Math.round(value)} tabIndex={0} className={'panel-resizer '+side}
 onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,value};document.documentElement.classList.add('resizing-panels');}}
 onPointerMove={e=>{if(drag.current)onChange(drag.current.value+(e.clientX-drag.current.x)*(side==='left'?1:-1));}}
 onPointerUp={e=>{drag.current=null;e.currentTarget.releasePointerCapture(e.pointerId);document.documentElement.classList.remove('resizing-panels');}}
 onLostPointerCapture={()=>{drag.current=null;document.documentElement.classList.remove('resizing-panels');}}
 onKeyDown={e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();onChange(value+(e.key==='ArrowRight'?20:-20)*(side==='left'?1:-1));}}}/>;
}
