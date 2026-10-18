export const ENTITY_TYPES = ['Person','Event','Task','Booking','Conversation','Message','Bot','Source','Claim','Decision','Action','Outcome'] as const;
export type EntityType = typeof ENTITY_TYPES[number];
export type Properties = Record<string, unknown>;
export interface GraphNode { id: string; type: EntityType; created_at: number; updated_at: number; properties: Properties }
export interface GraphEdge { id: string; type: string; source: string; target: string; created_at: number; updated_at: number; properties: Properties }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[]; paths: {node_ids: string[]; edge_ids: string[]}[]; truncated: boolean }
export interface EntityPage { items: GraphNode[]; next_offset: number | null }
export type ViewMode = 'network' | 'simple';
export type Selection = {kind:'node'|'edge'; id:string} | null;
export const TYPE_COLORS: Record<EntityType,string> = {Person:'#36a7e8',Event:'#a17ae9',Task:'#f6a534',Booking:'#33bdc7',Conversation:'#b2b5d6',Message:'#cad5df',Bot:'#f6a788',Source:'#efd563',Claim:'#f3c63f',Decision:'#ed73b4',Action:'#53cb90',Outcome:'#45c58a'};
export function nodeLabel(node: GraphNode): string { if(node.type==='Action'&&node.properties.record_kind==='APPROVAL_ACTION')return `${String(node.properties.tool||'Action').replace('action_task_update','Internal task change').replace('action_task_create','New internal task')} · ${String(node.properties.status||'proposed').replaceAll('_',' ').toLowerCase()}`; if(node.type==='Outcome')return `Outcome · ${String(node.properties.status||'unknown').toLowerCase()}`; return String(node.properties.name || node.properties.title || node.properties.text || node.properties.content || node.id); }
export const RELATION_LABELS: Record<string,string> = {PARENT_OF:'parent of',SIBLING_OF:'sibling of',ASSIGNED_TO:'assigned to',DEPENDS_ON:'depends on',RELATED_TO:'related to',PARTICIPATES_IN:'participates in',AFFECTS:'affects',MENTIONED_IN:'mentioned in',SUPPORTED_BY:'supported by',MOTIVATED_BY:'motivated by',MUTATED:'changed',PRODUCED:'produced',VERIFIED_BY:'verified by',HAS_CONVERSATION:'has conversation',HAS_MESSAGE:'has message',AUTHORED_BY:'authored by',SUPERSEDES:'supersedes'};
export function relationLabel(type: string) { return RELATION_LABELS[type] || type.toLowerCase().replaceAll('_',' '); }
