import {ENTITY_TYPES, type GraphData, type GraphNode, type EntityPage} from './models';

const API_BASE = (import.meta.env.VITE_ORBIT_API_URL || 'http://127.0.0.1:8001').replace(/\/$/,'');
export class GraphApiError extends Error { constructor(message:string, public status=0) { super(message); } }
async function request(path:string, signal:AbortSignal, body?:object):Promise<unknown> {
  const timeout = new AbortController();
  const abort = () => timeout.abort();
  signal.addEventListener('abort',abort,{once:true});
  if(signal.aborted) timeout.abort();
  const timer = setTimeout(()=>timeout.abort(),12000);
  try {
    const response = await fetch(API_BASE+path,{signal:timeout.signal, cache:'no-store',
      headers:{'Content-Type':'application/json',...(localStorage.getItem('orbit.chat.mode')!=='normal'&&localStorage.getItem('orbit.story.workspace')?{'X-Orbit-Story':localStorage.getItem('orbit.story.workspace')!}:{})},
      ...(body ? {method:'POST',body:JSON.stringify(body)} : {})});
    const data = await response.json();
    if(!response.ok) throw new GraphApiError(response.status===503
      ? 'FalkorDB is unavailable. Start the database with docker compose up -d, then refresh.'
      : data.error?.message || `Graph request failed (${response.status}).`,response.status);
    return data;
  } catch(error) {
    if(signal.aborted) throw new DOMException('Request cancelled','AbortError');
    if(error instanceof GraphApiError) throw error;
    throw new GraphApiError(timeout.signal.aborted
      ? 'The graph request timed out. Try fewer hops or check the backend connection.'
      : 'Cannot reach the ORBIT graph API. Start the backend on port 8001 and check VITE_ORBIT_API_URL.');
  } finally {clearTimeout(timer);signal.removeEventListener('abort',abort);}
}
function isNode(n:any):n is GraphNode {
  return n && typeof n.id==='string' && ENTITY_TYPES.includes(n.type) && Number.isFinite(n.created_at)
    && Number.isFinite(n.updated_at) && n.properties && typeof n.properties==='object' && !Array.isArray(n.properties);
}
export function validateGraph(data:any):GraphData {
  if(!data || !Array.isArray(data.nodes) || !data.nodes.every(isNode) || !Array.isArray(data.edges)
      || typeof data.truncated!=='boolean' || !Array.isArray(data.paths)) throw new GraphApiError('The backend returned an invalid graph response.');
  const ids=new Set(data.nodes.map((n:GraphNode)=>n.id));
  const edgeIds=new Set(data.edges.map((e:any)=>e.id));
  if(ids.size!==data.nodes.length || edgeIds.size!==data.edges.length || !data.edges.every((e:any)=>
    typeof e.id==='string' && typeof e.type==='string' && ids.has(e.source) && ids.has(e.target)
    && Number.isFinite(e.created_at) && Number.isFinite(e.updated_at) && e.properties && typeof e.properties==='object')
    || !data.paths.every((p:any)=>Array.isArray(p.node_ids)&&Array.isArray(p.edge_ids)
      && p.node_ids.every((id:string)=>ids.has(id))&&p.edge_ids.every((id:string)=>edgeIds.has(id))))
    throw new GraphApiError('The graph contains inconsistent entity or relationship references.');
  return data;
}
export const graphService = {
  async story(signal:AbortSignal):Promise<GraphData>{const data:any=await request('/api/story/state',signal);return validateGraph(data.graph);},
  async search(q:string,type:string,offset:number,signal:AbortSignal):Promise<EntityPage> {
    const params=new URLSearchParams({q,offset:String(offset),limit:'30'});
    if(type) params.set('type',type);
    const data:any=await request('/api/nodes?'+params,signal);
    if(!data || !Array.isArray(data.items) || !data.items.every(isNode) || !(data.next_offset===null || Number.isInteger(data.next_offset)))
      throw new GraphApiError('The backend returned an invalid entity list.');
    return data;
  },
  async subgraph(root:string,hops:number,signal:AbortSignal):Promise<GraphData> {
    return validateGraph(await request('/api/graph/subgraph',signal,{root_id:root,hops,direction:'both',limit:100}));
  },
};
// Phase 03 can call this after a successful graph mutation. No polling or mocks.
export function invalidateGraph() { window.dispatchEvent(new Event('orbit:graph-changed')); }
