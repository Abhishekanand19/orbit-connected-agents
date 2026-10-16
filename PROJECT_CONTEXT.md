# Project Context

## Goal

Build ORBIT, a premium multi-agent AI application for Graph Hacks 2026, Track 01: Agents That Act on Connected Data, powered by FalkorDB. The intended product remembers connected context, collaborates through specialized agents, and eventually performs approved, verified actions with traceable evidence. Real graph operations and real provider/tool calls must support all demonstrations; visual decoration and simulated success are not substitutes.

## Architecture

- Frontend: React 19, Vite 6, existing JSX chat workspace with original SVG avatars, custom bots, settings and separate conversations. New graph modules use TypeScript. Styling is the existing premium dark interface.
- Graph rendering: React Flow (`@xyflow/react`) and Dagre (`@dagrejs/dagre`). Both modes consume one shared graph snapshot.
- Backend: Python, FastAPI, Pydantic and the official FalkorDB Python client. Graph queries are centralized in repository modules. HTTPX calls Gemini from the backend only.
- Database: Docker Compose FalkorDB on loopback port 6380, persistent named volume. This is separate from the older PathLock database on 6379.
- Local application: frontend `http://127.0.0.1:5173`; API `http://127.0.0.1:8001`; OpenAPI `/docs`.
- Configuration: root `.env`, loaded by `backend/orbit/config.py`. Default graph is `orbit`; the existing seeded graph is `orbit_test_demo`. Check `/api/health` to see the actual active graph. Environment variables override dotenv values.
- LLM: Gemini implemented, configurable through `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) and `GEMINI_MODEL`. OpenAI is not implemented. Last successful live tests used `gemini-3.5-flash-lite` configured locally; the code fallback remains `gemini-2.5-flash`.

Important paths:

| Path | Responsibility |
|---|---|
| `frontend/src.jsx`, `frontend/style.css` | Existing chat, bot configuration and graph launch controls |
| `frontend/src/services.js` | Local workspace settings, backend chat transport and message mapping |
| `frontend/src/graph/GraphWorkspace.tsx` | Shared graph snapshot, search, depth, refresh and mode switching |
| `frontend/src/graph/GraphCanvas.tsx`, `layout.ts` | Network/tree rendering and cycle-safe layout |
| `frontend/src/graph/service.ts`, `models.ts`, `Inspector.tsx` | Typed API boundary, graph models and actual properties/evidence |
| `backend/orbit/api.py`, `models.py`, `service.py` | HTTP endpoints, typed contracts and graph domain validation |
| `backend/orbit/repository.py`, `database.py` | Parameterized Cypher, client lifecycle and persistence |
| `backend/orbit/llm.py` | Real Gemini HTTP calls and sanitized provider errors |
| `backend/orbit/extraction.py` | Structured extraction, validation, entity reuse and source-backed claims |
| `backend/orbit/memory.py` | Bounded relevant graph retrieval and prompt context limits |
| `backend/orbit/chat.py` | Persistent user/assistant turns, extraction journal and retry identities |
| `tests/orbit/` | Real FalkorDB backend tests, live chat tests and isolated browser fixture |
| `frontend/src/graph.spec.js` | Actual API/rendered graph parity and live chat-to-graph verification |
| `compose.yaml`, `start-orbit.ps1` | Database and API startup |

## Completed

### Phase 01 — FalkorDB foundation

Persistent typed graph APIs, stable IDs, bounded 1–4-hop traversals, directed relationships, provenance, immutable messages/claims, claim supersession and an explicit optional seed. Earlier verification: 11 backend tests passed. These were not all rerun during Phase 03.

### Phase 02 — Graph View and Simple View

Two header buttons open a spacious dismissible workspace. Implemented search, type filtering, depth selection, node/edge inspection, pan, zoom, fit, dragging, path highlighting, branch collapse and refresh. Simple View uses the same actual graph with a top-down projection; cross-links, cycles and stored direction are preserved without duplicate entities. Empty/error states do not substitute mock data.

Earlier verification: six graph browser tests, four chat browser tests, two frontend unit tests, typecheck and build passed at that stage. A subsequent live test added a temporary relationship to `orbit_test_demo`, refreshed both modes, verified its exact ID and direction, then removed it.

### Phase 03 — Real LLM chat and graph-memory foundation

Implemented real Gemini chat, bot instructions, backend message persistence, structured extraction, shared graph retrieval, source-backed facts, pending/confirmed states, supersession, stable retry IDs and graph invalidation after chat. Legacy local messages can be imported when starting a backend conversation. New conversations preserve prior graph evidence. No assistant-generated claims are intentionally extracted.

Extracted relationships are represented as Claim nodes connected to their subjects and Source/Message evidence, rather than unconditional direct facts between entities. Semantic relation descriptions are in claim text. Current extraction entity types are Person, Event, Task and Booking.

Latest focused verification: **6 backend chat tests and 1 browser integration test passed; production build passed.** Live Gemini/FalkorDB tests verified tentative and confirmed claims, entity reuse, superseded evidence, repeated request identity, a new conversation/second bot recalling shared context, and hypothetical/question messages adding no facts in the tested cases. The browser test sent a real chat message, checked the reply after reload, and compared both graph modes' IDs to backend responses. Missing-key, rate-limit, provider-failure and timeout tests use controlled failures; they are not claims of actual provider outages for those test cases.

## Current State

Phases 01–03 are implemented. Long-term memory has a working foundation, but Phase 04 is not complete. Bots share graph context and have distinct instructions; they do not collaborate or delegate work yet.

The last running API used `orbit_test_demo`. Its original explicit seed had 10 nodes and 13 relationships; do not assume these counts remain fixed after real chat writes. The default `orbit` graph was empty during diagnosis. Neither view chooses the seed automatically.

Start Docker Desktop, then run `docker compose up -d --wait`. In a root PowerShell terminal, choose the intended graph explicitly if needed (`$env:FALKORDB_GRAPH = 'orbit_test_demo'`) and run `./start-orbit.ps1`. In another terminal run `npm run dev` from `frontend`. Do not reseed an existing graph merely because the UI is empty; check API health and configuration first.

Focused checks: `.venv/Scripts/python.exe -m pytest tests/orbit/test_chat.py -q`; from `frontend`, `npm run test:graph -- --grep "live chat extraction"` and `npm run build`. Live chat tests require a usable provider key and incur real API calls. Graph browser tests use Edge and isolated servers on 8002/5174 with a temporary real database graph cleaned up afterward.

## Important Decisions

- FalkorDB is the authoritative memory store. LocalStorage remains useful for bot appearance/settings and a UI cache, not the sole source of conversation memory.
- Both graph modes must keep using the same backend topology. Layout must never reverse edge meaning, invent links or replace missing data with mocks.
- Graph traversal uses bounded hops/path counts. Returned subgraphs are unions of paths, not guaranteed induced subgraphs containing every edge between returned nodes.
- Preserve stable entity/relationship/message IDs and prior evidence. Corrections create superseding claims; old evidence is not overwritten or silently deleted.
- CONFIRMED means explicitly asserted by the user, not independently verified truth. Pending, ambiguous, hypothetical and assistant-generated information must not become confirmed merely because it is reachable in the graph.
- API keys belong exclusively on the backend, never in frontend bundles, logs, screenshots or tracked templates. `.env` is ignored. A key was pasted into the conversation; rotation was advised, but completion of rotation is not verified.
- Preserve the current UI and architecture. Implement incremental phases rather than redesigning or rebuilding.
- Maintain separate conversations per bot and shared authorized graph memory. The current app is a single-user, loopback development application, not a secure multi-user service.

## Known Bugs

Resolved issues and attempted fixes:

- Empty graph UI: API was connected to empty `orbit`, while existing data was in `orbit_test_demo`. Switching backend graph configuration fixed it without reseeding.
- Credential detection: an earlier check incorrectly rejected an `AQ...` key prefix. Actual Gemini authentication returned HTTP 200. Do not infer validity from a prefix. The configured value was moved from `.env.example` into ignored `.env`, and removed from the tracked template.
- Gemini rejected the initial structured-output schema as too complex. Provider-facing size constraints were simplified; local Pydantic validation remains. Evidence reference failures prompted stricter quote constraints, subject-reference normalization and one bounded extraction repair attempt.
- `gemini-2.5-flash` returned real temporary 503 overload errors. A trial of `gemini-2.5-flash-lite` returned 404 for new users. Local configuration was changed to the provider-recommended `gemini-3.5-flash-lite`, which passed subsequent live tests.

Known limitations / risks to address, not verified fixes:

- Retrieval is lexical search plus bounded neighborhoods and recent messages. It is not comprehensive long-term recall, semantic retrieval, durable summarization or a memory-ranking system.
- Exact unique type/name matching helps reuse entities but can conflate different people with the same name. Alias resolution and ambiguity handling need dedicated Phase 04 work.
- Extraction remains probabilistic. Passing focused examples does not guarantee correct treatment of every contradiction, speculation or prompt injection.
- Decision/action/outcome schemas exist, but automatic extraction currently does not persist these categories. No actions or decisions are executed.
- Chat uses a process-local global lock. Retry journaling supports resuming partial work, but the complete turn is not one atomic transaction and there is no distributed locking. Keep a single API worker until this is addressed.
- Old local history migration is capped at 500 messages per request. Bot appearance/custom-bot discovery still relies on browser storage; complete cross-device workspace restoration is not implemented.
- The code's fallback Gemini model differs from the locally successful configured model; preserve/verify `GEMINI_MODEL` when restarting elsewhere.
- Existing Phase 01/02 tests predate the new chat behavior. The old full UI suite was not rerun after Phase 03; some assertions about disconnected AI/local-only messages may need focused updates.
- Nonfatal observed warnings: Starlette/httpx TestClient deprecation and Vite ignoring React Flow's `use client` directive.

## Next Task

**Implement Phase 04 only: long-term memory.** Extend the existing Phase 03 foundation rather than replacing it. Remember and retrieve important facts, people, commitments, prior decisions and recorded action outcomes across sessions and individual bots.

The next session should:

1. Inspect the focused memory/extraction/chat modules and tests, then define durable memory behavior around existing IDs, claims and provenance.
2. Improve entity identity and ambiguity handling, relevant retrieval/ranking, temporal commitments, contradiction/supersession handling and long-history recall beyond the current lexical/recent-message window.
3. Support storing/retrieving explicitly supplied historical decisions and outcomes without implementing a decision engine or executing actions.
4. Verify memory after a genuine backend restart and from a new conversation with a different bot. Include old facts beyond the recent-message window, same-name ambiguity, duplicate requests and corrections with preserved evidence.
5. Keep prompt context bounded, graph views synchronized through existing APIs, and live-provider claims grounded in executed tests. Report limitations honestly and stop after Phase 04.

Remaining roadmap (user-defined order):

| Phase | Remaining work |
|---|---|
| 04 — Long-term memory | Facts, people, commitments, previous decisions and action outcomes across sessions and individual bots |
| 05 — Multi-agent collaboration | Coordinator, Planner, Research, Communication and Task agents with distinct responsibilities and shared FalkorDB state |
| 06 — Graph intelligence engine | Extend existing traversal/provenance with conflict detection, dependencies, confidence states and graph-based decision making |
| 07 — MCP tools and app integrations | Working Google Calendar, Gmail and one useful messaging/task integration; graph-informed tool selection |
| 08 — Real actions and approvals | Approval UI, calendar/message/task actions, confirmation handling, readback verification, deduplication and recovery |
| 09 — Decision Receipts and Why view | Human-readable triggering event, retrieved evidence, agent reasoning, selected tool and verified result |
| 10 — Proactive monitoring and routines (optional) | Monitor selected sources and trigger workflows; defer nonessential routines if time is limited |
| 11 — Family & Work Domino demo | Realistic seed, conflicting updates, genuine agent actions, second-session memory and live graph variation |
| 12 — Automated tests and deployment | Extend current tests/Docker setup with persistence, dependency, MCP and action-verification coverage plus reliable deployment instructions |
| 13 — GitHub and submission package | Professional README, architecture, Cypher examples, evidence matrix, reproducible demo and five-minute YouTube video |

## Constraints

- Do not start Phase 05 or later without authorization. Phase 04 must not introduce orchestration, MCP/external integrations, approvals, scheduling, execution, proactive routines or the Domino demo.
- Do not redesign chat, avatars, custom bots or either visualization. Preserve separate bot conversations and backwards-compatible Phase 01 APIs.
- Do not modify the older PathLock implementation, its database, or unrelated project files.
- Preserve existing user edits. Inspect working-tree state before changing files; do not reset or overwrite changes based on this context document.
- No automatic commits. The latest implementation request also prohibited README updates, new documentation and long reports; this file is an explicit exception requested afterward. Do not infer permission to rewrite submission docs.
- Use typed validation and parameterized Cypher. Keep model transport, extraction, retrieval and persistence independently discoverable. Do not expose arbitrary Cypher through public endpoints.
- Use targeted tests appropriate to the change, isolated `orbit_test_*` graphs and real provider calls when claiming live behavior. Do not repeatedly run unrelated suites, fabricate benchmarks or hide skipped/failed checks.
- Do not delete production/demo evidence for tests or use `docker compose down -v` as routine cleanup. Never silently seed or substitute fake graph data.
- Keep secrets private. Confirm credential presence or provider status without printing values. Verify current processes/configuration rather than assuming the last session's servers are still running.
