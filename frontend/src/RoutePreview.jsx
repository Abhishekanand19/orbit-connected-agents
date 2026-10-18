import React,{useRef} from 'react';

export default function RoutePreview(){
 const dialog=useRef(null);
 const description='Static demo route preview · not a verified route or Uber booking';
 return <figure className="route-preview">
  <button type="button" aria-label="Enlarge route preview" onClick={()=>dialog.current.showModal()}><img src="/brand/demo-route.png" alt="Provided map route screenshot"/></button>
  <figcaption>{description}</figcaption>
  <dialog ref={dialog} className="route-enlarged" aria-label="Enlarged route preview" onClick={e=>{if(e.target===e.currentTarget)dialog.current.close();}}>
   <button type="button" onClick={()=>dialog.current.close()}>Close preview</button>
   <img src="/brand/demo-route.png" alt="Provided map route screenshot enlarged"/>
   <p>{description}</p>
  </dialog>
 </figure>;
}
