
# ORBIT

ORBIT combines a dark React chat workspace with a persistent FalkorDB graph foundation. Phase 02 adds two interactive, read-only projections of actual backend graph data. Chat messages still use local browser storage; they do not extract facts or update the graph.

## Run locally

Use Python 3.10+, Node.js and Docker Desktop. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/orbit/requirements.txt
docker compose up -d --wait
.\start-orbit.ps1
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The API runs at http://127.0.0.1:8001; its interactive contract is at `/docs`. See [.env.example](.env.example) and [the graph schema](docs/orbit-graph-schema.md). The isolated Compose database uses port 6380 and a persistent volume. `docker compose down` retains its data; `docker compose down -v` deletes it.

An empty database displays an empty state. To explicitly populate the optional backend sample, stop the API, run the following, then restart it in that same terminal:

```powershell
.\.venv\Scripts\python.exe -m backend.orbit.seed --graph orbit_test_demo
$env:FALKORDB_GRAPH = 'orbit_test_demo'
.\start-orbit.ps1
```

This seed is stored in FalkorDB, never generated in the visualization. It is an optional test fixture, not an implemented action demo. The older PathLock files are retained separately; use the ORBIT commands above.

## Graph Visualization

Click **Graph View** or **Simple View** in the chat's top-right header. Both open the same spacious workspace; switch modes without fetching a different graph, or close it to return to chat. Search for an entity, choose 1–4 hops, filter by type, inspect a node or relationship, and use **Explore from here** to change focus. Drag to arrange or pan, scroll to zoom, and use the fit control to reframe.

- **Graph View:** circular type-colored nodes, stored relationship labels and arrows, draggable positions, and highlighted paths from the focus to the selected entity.
- **Simple View:** top-down rounded cards, expandable branches, human-readable relationship labels, and dashed cross-links with a shared-connections strip. Dagre lays out a breadth-first spanning tree for placement only. Every entity appears once; cycles and shared relationships retain their stored endpoints and direction. Branch placement and highlighted reachability do not assert dependency or causality.
- **Inspector:** actual properties, timestamps, claim status, available evidence/mentions, connected entities and stored relationship direction. Full text remains available here when a canvas label is shortened.

Both modes are implemented in [GraphCanvas.tsx](frontend/src/graph/GraphCanvas.tsx), with [EntityNode.tsx](frontend/src/graph/EntityNode.tsx), [RelationshipEdge.tsx](frontend/src/graph/RelationshipEdge.tsx), and the separate layout/projection algorithm in [layout.ts](frontend/src/graph/layout.ts). [GraphWorkspace.tsx](frontend/src/graph/GraphWorkspace.tsx) owns their single shared snapshot. Rendering uses React Flow and Dagre; graph modules are lazy-loaded when opened.

The typed [service.ts](frontend/src/graph/service.ts) consumes:

| API | Use |
|---|---|
| `GET /api/nodes?q=…&type=…&offset=…&limit=30` | Paginated entity discovery from FalkorDB; the only added backend endpoint |
| `POST /api/graph/subgraph` | Actual nodes, directed edges and paths for the selected root; `direction: both`, 1–4 hops, 100-path limit |

The default is a focused two-hop subgraph, not the entire database. A subgraph is the union of returned traversal paths; it need not contain every edge between its nodes. A visible notice reports truncation. Type filtering retains the focus and hides edges whose endpoints are hidden; it never invents substitute links. Collapsing branches reports hidden counts. Search queries the backend independently of the displayed neighborhood.

**Refresh** reloads both the directory and graph. Reopening fetches a new snapshot. Superseded requests are cancelled, and failed requests remove stale graph content and show a helpful connection error. There is no mock fallback or background polling. Future graph writers can call `invalidateGraph()` after successful mutations; LLM extraction is not implemented. To use another API address, set `VITE_ORBIT_API_URL` before starting Vite and allow its origin in `ORBIT_ALLOWED_ORIGINS` on the backend.

### Verify synchronization

Open either view on an entity. Through `/docs`, create/update a permitted relationship or remove one with the existing relationship APIs. Click Refresh and inspect the stored type, direction and properties. Switch views to see the same snapshot, then close/reopen to retrieve it again. The automated mutation test performs a real reassignment and verifies old/new edge IDs in both modes and after reopening.

```powershell
# Root: real FalkorDB must be running
.\.venv\Scripts\python.exe -m pytest tests/orbit -q
cd frontend
npm run typecheck
npm run build
npm test
npm run test:graph
# Existing chat browser regression tests (keep npm run dev running)
npx playwright test
```

Browser tests use installed Microsoft Edge. Graph tests start a separate API on 8002 and Vite on 5174, explicitly seed a unique `orbit_test_visuals_*` database graph, and delete that graph during teardown. They do not seed or clear the configured application graph. Screenshots are generated under `frontend/test-results/`; they are test artifacts, not benchmark evidence.

### Implementation Evidence Matrix

| Capability | Implementation | Verification |
|---|---|---|
| Real entity discovery | `backend/orbit/api.py`, `backend/orbit/repository.py`: `search_nodes` | `tests/orbit/test_foundation.py`: discovery search, type filter and pagination |
| Real multi-hop topology | `backend/orbit/repository.py`, `frontend/src/graph/service.ts`, `models.ts` | `tests/orbit/test_foundation.py`; `frontend/src/graph.spec.js` compares rendered node/edge IDs to API responses |
| Network and hierarchical projections | `frontend/src/graph/GraphCanvas.tsx`, `layout.ts`, `EntityNode.tsx`, `RelationshipEdge.tsx` | `graph.spec.js`: both modes, root placement, cycles/self-links/shared connections, collapse/expand |
| Direction, properties and provenance | `frontend/src/graph/Inspector.tsx`, `RelationshipEdge.tsx` | `graph.spec.js`: stored assignment endpoints/type and pending claim evidence |
| Current graph after mutations | `frontend/src/graph/GraphWorkspace.tsx`, `service.ts` | `graph.spec.js`: real API reassignment, refresh, switch and reopen |
| Exploration and failure states | `GraphWorkspace.tsx`, `GraphCanvas.tsx`, `service.ts` | `graph.spec.js`: search, filter, zoom, drag, focus, rapid depth changes, interrupted request/recovery, actual empty graph, mobile |
| Existing chat preserved | `frontend/src.jsx`, `frontend/src/services.js` | Existing frontend unit/browser suites; graph test closes back to chat |

Completed: Phase 01 persistence, typed APIs, bounded traversals and provenance; Phase 02 shared graph workspace and both visualization modes. Planned, **not implemented**: LLM chat, automatic extraction, orchestration, MCP, external integrations, decisions, approvals, action execution and monitoring. Local API authentication and multi-user isolation remain outside these phases.
