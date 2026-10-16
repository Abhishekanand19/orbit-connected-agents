export const ENTITY_TYPES = ['Person','Event','Task','Booking','Conversation','Message','Bot','Source','Claim','Decision','Action','Outcome'] as const;
export type EntityType = typeof ENTITY_TYPES[number];
export type Properties = Record<string, unknown>;
export interface GraphNode { id: string; type: EntityType; created_at: number; updated_at: number; properties: Properties }
export interface GraphEdge { id: string; type: string; source: string; target: string; created_at: number; updated_at: number; properties: Properties }
export interface GraphData { nodes: GraphNode[]; edges: GraphEdge[]; paths: {node_ids: string[]; edge_ids: string[]}[]; truncated: boolean }
export interface EntityPage { items: GraphNode[]; next_offset: number | null }
export type ViewMode = 'network' | 'simple';
export type Selection = {kind:'node'|'edge'; id:string} | null;
export const TYPE_COLORS: Record<EntityType,string> = {Person:'#c2ade4',Event:'#edaa89',Task:'#a7c49b',Booking:'#8dbed0',Conversation:'#b2b5d6',Message:'#b2bec3',Bot:'#e1b577',Source:'#9bc9b6',Claim:'#e0c77f',Decision:'#cf9cbd',Action:'#c2af9f',Outcome:'#96c7ba'};
export function nodeLabel(node: GraphNode): string { return String(node.properties.name || node.properties.title || node.properties.text || node.properties.content || node.id); }
export const RELATION_LABELS: Record<string,string> = {ASSIGNED_TO:'assigned to',DEPENDS_ON:'depends on',RELATED_TO:'related to',PARTICIPATES_IN:'participates in',AFFECTS:'affects',MENTIONED_IN:'mentioned in',SUPPORTED_BY:'supported by',MOTIVATED_BY:'motivated by',MUTATED:'changed',PRODUCED:'produced',VERIFIED_BY:'verified by',HAS_CONVERSATION:'has conversation',HAS_MESSAGE:'has message',AUTHORED_BY:'authored by',SUPERSEDES:'supersedes'};
export function relationLabel(type: string) { return RELATION_LABELS[type] || type.toLowerCase().replaceAll('_',' '); }
