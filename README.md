## FalkorDB Foundation

ORBIT has a separate local FastAPI backend in `backend/orbit/`. The existing frontend and legacy PathLock/AWS backend are preserved. No LLM, agent, integration or visualization functionality is added in this phase.

### Run

From the repository root (Python 3.10+ and Docker Desktop required):

```powershell
# Create .venv first if needed: python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/orbit/requirements.txt
# Optional: copy .env.example to .env and customize it.
docker compose up -d --wait
.\start-orbit.ps1
```

Backend: http://127.0.0.1:8001/docs; health: http://127.0.0.1:8001/api/health. The default graph is `orbit`. Docker publishes FalkorDB on `127.0.0.1:6380`, independently of the old PathLock instance on port 6379. `orbit-foundation_orbit_graph_data` persists data with AOF. Stop with `docker compose down`; do not add `-v` unless intentionally deleting the data.

Frontend remains independent: `cd frontend`, `npm run dev`. It still uses localStorage.

### Seed and sample traversal

Seed data is optional, idempotent, restricted to an explicitly named test graph, and never runs during startup:

```powershell
.\.venv\Scripts\python.exe -m backend.orbit.seed --graph orbit_test_demo
# Start the API against that test graph (stop any existing API on 8001 first):
$env:FALKORDB_GRAPH = 'orbit_test_demo'
.\start-orbit.ps1
```

In another terminal:

```powershell
$body = '{"root_id":"sample:appointment","hops":3,"relationship_types":["DEPENDS_ON","ASSIGNED_TO"]}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/graph/traverse -ContentType 'application/json' -Body $body
```

The sample traverses appointment → transport → person ← work commitment. It includes two people, one appointment, one booking, one work task, a bot/conversation/message and a source-backed `PENDING` claim. These are testing fixtures, not application logic. Assignment assertions default to `UNVERIFIED`.

### Schema and queries

Core nodes: Person, Event, Task, Booking, Conversation, Message, Bot, Source, Claim, Decision, Action, Outcome. Relationships: ASSIGNED_TO, DEPENDS_ON, RELATED_TO, PARTICIPATES_IN, AFFECTS, MENTIONED_IN, SUPPORTED_BY, MOTIVATED_BY, MUTATED, PRODUCED, VERIFIED_BY, plus managed HAS_CONVERSATION, HAS_MESSAGE, AUTHORED_BY and SUPERSEDES.

See [schema, edge directions and API contract](docs/orbit-graph-schema.md). Actual parameterized Cypher is in `backend/orbit/repository.py`; client lifecycle and uniqueness constraints are in `backend/orbit/database.py`. Responses expose stable IDs, nodes, edges and actual ordered paths, ready for later graph/tree views. Traversals are limited to four hops, 500 returned paths and a configurable database timeout. Claims preserve provenance and supersession history; generic writes cannot overwrite historical claims/messages.

### Tests and verified results

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orbit -q -s
# Optional: recreates only ORBIT's DB container, retaining the volume:
.\.venv\Scripts\python.exe -m backend.orbit.verify_persistence --graph orbit_test_demo --recreate-container
cd frontend
npm run build
npm test
# With frontend dev server running:
npx playwright test
```

Integration tests use real FalkorDB and isolated `orbit_test_<uuid>` graphs, removed after each test. An unavailable DB causes test failure, not a fake pass or silent skip. Run `tests/orbit` explicitly; `tests/test_live.py` belongs to the old AWS sandbox and is not part of ORBIT testing.

Verified in this implementation: 10 backend integration tests passed; container recreation preserved all properties of 10 seeded nodes and 13 edges; frontend production build, 2 storage tests and 4 browser tests passed. The mutation test actually changed the transport assignment in FalkorDB: the same traversal returned appointment/transport/Priya/work before, and appointment/transport/Dad afterwards. The test prints these actual results. One installed Starlette/httpx test-client deprecation warning is non-failing.

### Implementation Evidence

| Feature | Actual source and function | Executed test |
|---|---|---|
| Official client, health, outage handling | `backend/orbit/database.py`: `Database.initialize`, `execute`, `close`; `backend/orbit/api.py`: `health` | `tests/orbit/test_foundation.py`: `test_health_upserts_edges_and_concurrent_identity`, `test_database_unavailable_returns_503_and_safe_startup` |
| Stable nodes/edges and idempotent upserts | `backend/orbit/repository.py`: `upsert_node`, `upsert_edge`, `edge_id` | `test_health_upserts_edges_and_concurrent_identity`, `test_seed_is_idempotent` |
| Bounded graph traversal and evidence paths | `backend/orbit/repository.py`: `traverse`; `backend/orbit/service.py`: `dependencies`, `affected` | `test_real_relationship_mutation_changes_multihop_results`, `test_four_hop_boundaries_and_unverified_assignments` |
| Claims, provenance and supersession | `backend/orbit/service.py`: `create_claim`, `evidence`; `backend/orbit/repository.py`: `atomic_record` | `test_claim_provenance_supersession_and_no_silent_rewrite`, `test_competing_claim_updates_are_atomic` |
| Linked conversations and messages | `backend/orbit/service.py`: `create_conversation`, `create_message`, `conversation_context` | `test_conversation_message_context_atomicity_and_pagination` |
| Persistence | `compose.yaml`; `backend/orbit/verify_persistence.py`: `snapshot` | `test_restart_persistence_in_fresh_backend_process`; executed container recreation check |
| Input validation and errors | `backend/orbit/models.py`; `backend/orbit/api.py`: `invalid_request`, `graph_error` | `test_invalid_input_conflicts_missing_and_parameterization` |

All named integration tests live in `tests/orbit/test_foundation.py`.

**NOT IMPLEMENTED:** LLMs/fact extraction, orchestration, MCP, external integrations, automated planning/actions, approvals, routines, Graph View or Simple View. The backend is local-only, without authentication or multi-user isolation. Phase 02 can consume the documented graph responses; the frontend has not yet been connected to them.

---

> **ORBIT Phase 1 frontend:** See [frontend/README.md](frontend/README.md). Run `cd frontend` then `npm run dev`. The legacy PathLock backend documentation below remains for reference.

# PathLock

Connected context → minimum safe action → verified outcome.

PathLock is a working, deliberately small AWS permission demo with a local FalkorDB context engine. Order Support reads fake order 582 from DynamoDB. Its Lambda execution role can assume a second role that reads a fake Secrets Manager secret. The forbidden probe executes inside that Lambda; the browser never receives the secret.

## Run

Prerequisites: Python 3.10+, Node.js, AWS CLI with the project-local `pathlock` login, FalkorDB at localhost:6379 with graph `pathlock`.

```powershell
. .\aws-project.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
.\start.ps1
```

Open http://127.0.0.1:8000. The API is local and the Lambda exposure probe has no public URL. The demo starts with the current real cloud state. Analyze Cloud → Verify Exposure → Find Safe Fix → Approve & Apply. Each button calls the backend. AWS propagation can take time; failed operations are not reported as successes.

## Why a graph

Individually plausible permissions form a dangerous multi-hop route. FalkorDB stores AWS relationships, protected capabilities, ownership, findings, decisions, approvals and verification. The Investigator persists findings; the Remediator reads those findings and stored business constraints. It evaluates candidate cuts with deterministic reachability. Bedrock Nova Micro explains the evidence; its text cannot grant approval, apply permissions or set verification results.

## Real remediation

An explicit deny of `sts:AssumeRole` on the single demo target role replaces `DemoUnsafeRoute`. Removing an identity Allow alone is insufficient when a same-account role directly trusts the source role. The implementation was tested against this behavior. The order permission is preserved. The backend reruns both Lambda operations and records success only when secret access is denied and order 582 is SHIPPED. The previous policy is retained under ignored `.aws/rollback-policy.json`.

## Persistent memory

The second session creates a distinct Reporting Access role and retains the first analytics containment. It loads stored verification, ownership and the protected Order Lookup constraint. A new graph finding is passed to the planner. The UI shows four compact context items rather than chat history.

## Current verification

- Phase 1: real DynamoDB order and secret-access probe passed.
- Phase 2: FalkorDB retrieved the observed permission path.
- Phases 3–4: finding persisted; three candidate interventions evaluated; only the narrow intervention preserved Order Lookup.
- Phase 5: actual deny applied; identical probe denied; order still SHIPPED; result stored.
- Phase 6: reporting route provisioned and tested, with previous context loaded.
- Phase 7: React interface connects to real API operations; browser smoke tests passed through the reporting approval preview; the first remediation was verified through the backend.

## Boundaries and remaining hardening

This is a single-operator controlled sandbox, not a general IAM analyzer. Graph synchronization validates the known demo policies rather than evaluating arbitrary AWS policy combinations, SCPs or permission boundaries. The startup script assumes `pathlock-demo-controller`, whose runtime permissions are restricted to named demo resources and the Nova Micro model. The operator profile is used only to obtain that role session. The provisioning script deliberately refuses name collisions and is not a resumable deployment manager. Do not rerun provisioning against the existing sandbox. Second-session creation is one-shot. The UI is local, with no public API Gateway deployment. These are limitations, not simulated capabilities.

## Costs and cleanup

Real resources exist in ap-southeast-2: `pathlock-demo-order-support`, `pathlock-demo-orders`, `pathlock-demo-private-secret`, and roles prefixed `pathlock-demo-`. Secrets Manager storage, Lambda, DynamoDB and Bedrock may incur charges. Delete only these identified demo resources after the event. Do not delete the `Lift Off Soon` project or unrelated resources. Credentials and runtime state stay in ignored `.aws/`; never commit that directory.
