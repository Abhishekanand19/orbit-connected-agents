export const STORAGE_KEY = 'orbit.workspace.v1';
const oldColors=['#ed947e','#c3b1eb','#a8c6a0','#e8bd69','#9dbdd6','#df9db9'];
export const colors = ['#FF9278','#B38AFF','#6EDB87','#FFD16B','#62C5FF','#F38FC4'];
export const displayName=name=>({'Orbit Coordinator':'Coordinator','Schedule Planner':'Planner','Research Assistant':'Researcher'}[name]||name);
export const defaults = [
  ['coordinator', 'Orbit Coordinator', 'A little clarity for your everyday.', 'Understand requests and help coordinate the right specialist.', 0],
  ['planner', 'Schedule Planner', 'Make room for what matters.', 'Help organize appointments, plans and scheduling conflicts.', 1],
  ['research', 'Research Assistant', 'Follow your curiosity.', 'Research questions, compare options and gather reliable information.', 2],
  ['communication', 'Communication Assistant', 'Find the right words.', 'Help draft thoughtful messages, emails and conversations.', 3],
  ['tasks', 'Task Manager', 'Small steps. Things done.', 'Organize responsibilities, deadlines and task progress.', 4],
].map(([id, name, description, instructions, shape]) => ({ id, name:displayName(name), description, instructions, shape, color: colors[shape], notifications: false }));
export function freshWorkspace() { return { version: 1, bots: defaults.map(bot => ({...bot})), selectedId: 'coordinator', conversations: {} }; }
export function loadWorkspace(storage) {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (!raw) return {data: freshWorkspace(), error: ''};
    const data = JSON.parse(raw);
    if (data.version !== 1 || !Array.isArray(data.bots) || !data.bots.length || !data.conversations || typeof data.conversations !== 'object') throw Error('Invalid workspace');
    data.bots=data.bots.map(b=>({...b,name:displayName(b.name),color:oldColors.includes(b.color)?colors[oldColors.indexOf(b.color)]:b.color}));
    if (!data.bots.every(b => typeof b.id === 'string' && typeof b.name === 'string' && typeof b.description === 'string' && typeof b.instructions === 'string' && Number.isInteger(b.shape) && b.shape >= 0 && b.shape < 5 && colors.includes(b.color))) throw Error('Invalid bot');
    if (!Object.values(data.conversations).every(messages => Array.isArray(messages) && messages.every(m => typeof m.id === 'string' && typeof m.content === 'string' && ['user', 'assistant'].includes(m.role) && Number.isFinite(m.createdAt)))) throw Error('Invalid conversation');
    if (!data.bots.some(b => b.id === data.selectedId)) data.selectedId = data.bots[0].id;
    return {data, error: ''};
  } catch { return {data: freshWorkspace(), error: 'Your saved workspace could not be read. Changes will not overwrite it until you reload with valid storage.', blocked: true}; }
}
export function saveWorkspace(storage, data) {
  try { storage.setItem(STORAGE_KEY, JSON.stringify(data)); return ''; }
  catch { return 'Browser storage is unavailable or full. Your changes are only kept in this tab.'; }
}
// API boundary for a later phase. No generated replies are simulated.
export const chatService = { connection: 'unconfigured', createMessage(content) { return {id: crypto.randomUUID(), role: 'user', content: content.trim(), createdAt: Date.now()}; } };

export const STORY_KEY='orbit.story.workspace';
export function storyHeaders(){const id=localStorage.getItem('orbit.chat.mode')==='normal'?null:(sessionStorage.getItem(STORY_KEY)||localStorage.getItem(STORY_KEY));return id?{'X-Orbit-Story':id}:{};}
const CHAT_API = import.meta.env?.VITE_ORBIT_API_URL || 'http://127.0.0.1:8001';
export async function chatRequest(path, body) {
 const response=await fetch(CHAT_API+path,{...(body?{method:'POST',body:JSON.stringify(body)}:{}),headers:{'Content-Type':'application/json',...(path==='/api/story/workspaces'?{}:storyHeaders())},signal:AbortSignal.timeout(480000)});
 const data=await response.json();if(!response.ok)throw Error(data.error?.message||'Chat request failed. Please retry.');return data;
}
export const messageFromApi = n=>({id:n.id,role:n.properties.role,content:n.properties.content,createdAt:n.created_at,attachments:n.properties.attachments?JSON.parse(n.properties.attachments):[],story:n.properties.story?JSON.parse(n.properties.story):null});
export async function actionRequest(path,body){
 const response=await fetch(CHAT_API+path,{method:body===undefined?'GET':'POST',credentials:'include',cache:'no-store',headers:{'Content-Type':'application/json','X-Orbit-UI':'1',...storyHeaders()},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(130000)});
 const data=await response.json();if(!response.ok)throw Error(data.error?.message||'Action request failed. Refresh to check its saved status.');return data;
}
