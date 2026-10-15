# ORBIT graph schema and API contract

The graph is domain-independent. All entities carry `:Entity` plus one of `Person`, `Event`, `Task`, `Booking`, `Conversation`, `Message`, `Bot`, `Source`, `Claim`, `Decision`, `Action`, `Outcome`. The type is also stored as `entity_type` and returned as `type`. A database UNIQUE constraint on `Entity.id` prevents cross-type ID reuse, including concurrent writes.

## Identity, properties and time

Caller-provided IDs are stable strings of 1–128 characters matching `[A-Za-z0-9][A-Za-z0-9_.:-]*`. Reusing an ID identifies the same entity; names are not identity keys. The system does not perform fuzzy entity resolution. Repeated relationship upserts merge the same ordered `(source, type, target)` tuple; UUIDv5 produces the stable edge ID. Opposite directions are distinct edges, even for `RELATED_TO`.

Server `created_at` and `updated_at` are Unix epoch milliseconds. Observations, event times and deadlines are timezone-aware ISO 8601 strings. Creation timestamps are preserved during updates. Mutable upserts refresh `updated_at`, even if their supplied values are unchanged. Immutable record retries preserve all timestamps.

`models.py` contains the exact allowlists and limits. Mutable node writes patch only supplied properties; null, unknown and reserved properties are rejected. Common fields are `name` and `description`; type-specific fields include Person `email`, Event `starts_at/ends_at/location`, Task `due_at/status`, Booking `reference/status`, Bot `instructions`, Source `kind/uri/external_id/observed_at`, and Decision/Action/Outcome `summary`. These last three are historical data records only; nothing executes actions or makes decisions.

Conversations, messages and claims use dedicated APIs and immutable payloads. A repeated ID with different contents returns 409. Conversations have `title/bot_id`; messages have `role/content/conversation_id/bot_id`. References are checked before a single atomic statement creates the node and all required edges. Assistant messages can be explicitly supplied through the API, but the application never generates replies.

## Directed relationships

| Edge | Direction and meaning |
|---|---|
| `ASSIGNED_TO` | Task/Event/Booking → Person/Bot; explicit assignment assertion |
| `DEPENDS_ON` | Task/Event/Booking → Task/Event/Booking/Person; source requires target |
| `RELATED_TO` | Entity → Entity; explicit association, not causal inference |
| `PARTICIPATES_IN` | Person/Bot → Event/Conversation |
| `AFFECTS` | Entity → Entity; explicitly supplied influence, not inferred |
| `MENTIONED_IN` | Entity/Source/Claim → Message; original mention/evidence reference |
| `SUPPORTED_BY` | Claim/Decision → Source/Message/Claim |
| `MOTIVATED_BY` | Decision/Action → Claim/Decision |
| `MUTATED` | Action → Entity; historical record of a change |
| `PRODUCED` | Action → Outcome |
| `VERIFIED_BY` | Outcome/Claim → Source/Claim/Message |
| `HAS_CONVERSATION` | Bot → Conversation; managed by conversation creation |
| `HAS_MESSAGE` | Conversation → Message; managed by message creation |
| `AUTHORED_BY` | Assistant Message → Bot; user messages are not attributed to a bot |
| `SUPERSEDES` | New Claim → Earlier Claim; managed atomically by claim creation |

Generic edge properties are `note` and `evidence_state`, defaulting to `UNVERIFIED`. Evidence states are `UNVERIFIED`, `PENDING`, `CONFIRMED`, `REFUTED`, `SUPERSEDED`. Structural links record containment/provenance rather than asserting factual certainty and have no evidence state. A pending claim never promotes an assignment to confirmed. Traversal returns evidence states as stored; consumers must not equate reachability with truth.

Generic relationship writes validate endpoint types. Managed structural links and immutable claim/message links cannot be modified through that endpoint. Evidence and structural edges cannot be deleted. Mutable disconnected nodes can be deleted; connected nodes and immutable historical records cannot. Removing or reassigning a mutable domain edge uses DELETE followed by PUT; these two requests are not an atomic reassignment transaction.

## Claims and provenance

A claim requires `text`, one Source, `observed_at`, and at least one known subject. `status` defaults to `UNVERIFIED`; certainty is supplied explicitly, never inferred from text. `source_id` must identify a Source with `kind` and `observed_at`. Optional `message_id` creates Claim → Message and Source → Message links; that Message leads back to its original Conversation and Bot. Subjects connect through Claim → `RELATED_TO` → Entity.

A Source's cited properties become immutable. A source-backed claim update creates a new claim ID with `supersedes_id`. The atomic write creates `SUPERSEDES`, sets the prior claim's status to `SUPERSEDED`, and records `superseded_by`; prior text, source links and creation time remain. Competing replacements cannot both win. Repeating the winning request is safe. Claim status/text cannot be patched in place. To refute a prior claim, create a new `REFUTED` claim with evidence and `supersedes_id`.

Example: the explicit seed's “Priya might…” statement creates a `PENDING` claim. A later confirmation must be submitted as a new `CONFIRMED` claim with a new Source and the earlier claim's ID. No fact extraction or inference exists.

## HTTP API

Interactive OpenAPI docs: `http://127.0.0.1:8001/docs`.

| Method and route | Operation |
|---|---|
| GET `/api/health` | Execute a real read query; 503 if unavailable |
| PUT/GET/DELETE `/api/nodes/{id}` | Upsert, retrieve, delete an eligible entity |
| PUT `/api/relationships` | Upsert a typed relationship |
| GET/DELETE `/api/relationships/{id}` | Retrieve/remove an eligible relationship |
| GET `/api/nodes/{id}/neighbors` | Direct neighbors and actual connecting edges |
| POST `/api/graph/traverse` | Bounded traversal and actual ordered paths |
| POST `/api/graph/subgraph` | Same traversal contract for a focused subgraph |
| GET `/api/nodes/{id}/dependencies` | Directed `DEPENDS_ON` traversal; incoming or outgoing |
| GET `/api/nodes/{id}/affected` | Connected Person/Event/Task/Booking candidates plus supporting graph |
| POST/GET `/api/conversations[/{id}]` | Create/retrieve a conversation linked to a known Bot |
| POST/GET `/api/conversations/{id}/messages` | Persist or paginate messages, ordered by creation time and ID |
| GET `/api/conversations/{id}/context` | Up to four hops, including mentions, related entities and available decisions |
| POST `/api/claims` | Atomic explicit claim and provenance creation/supersession |
| GET `/api/evidence/{id}` | Up to four evidence/provenance hops for Source/Claim/Decision/Outcome |

Traversal body: `root_id`, `hops` (1–4), `direction` (`both`, `outgoing`, `incoming`), optional `relationship_types`, optional `target_id`, `limit` (1–500 paths, default 100). With `target_id`, only paths reaching that node are returned. Results include the root even when no path exists. `target_id` is the evidence-path API; paths are real traversals, not shortest-path guarantees.

Response: `{nodes: [{id,type,created_at,updated_at,properties}], edges: [{id,type,source,target,created_at,updated_at,properties}], paths: [{node_ids,edge_ids}], truncated}`. Edge direction always reflects storage, even when traversing incoming or both directions. The subgraph is the union of returned paths, not every possible edge among returned nodes. Traversals are capped by hops, path count and database execution timeout. `truncated` indicates the path limit was reached; limited selection order is not guaranteed. Large dense graphs may time out and return 503 rather than partial success.

`affected` returns **connected candidates**, not proven causal effects or a plan. Evidence retrieval retains superseded claims for inspection. Conversation context is bounded, so decision evidence beyond its radius must be retrieved separately through `/api/evidence/{decision_id}`.

Known application errors use `{error: {code,message}}`, with validation details on 422. Missing entities return 404, identity/history conflicts 409, incompatible types/inputs 422, and DB failures 503. No arbitrary Cypher endpoint is exposed. Query values use parameters; dynamic type tokens come only from enums, and interpolated hop counts are bounded integers.

## Operations and boundaries

`Database.initialize` waits for the identity constraint to become operational. Missing database connectivity does not crash the HTTP service; operations return 503 and retry initialization on later requests. Sync queries run in FastAPI's worker pool; lifespan initialization uses a worker thread. Client sockets have configurable connection/read timeouts and close on shutdown. Failed writes are not reported as successful; an ambiguous client timeout can be retried using the same stable ID.

The Compose database is pinned by image digest, loopback-only, and isolated from PathLock on port 6380. The named volume mounts `/var/lib/falkordb/data`; AOF uses `appendfsync everysec` (abrupt host failure can lose roughly the latest second). Container recreation and backend-process restart persistence are tested. This is not a backup or high-availability implementation. `docker compose down` retains data; `docker compose down -v` deletes it.

The local API has an origin guard but no authentication, user isolation or production deployment hardening. Run it bound to loopback. Frontend data is deliberately not migrated or automatically synchronized. API records survive browser refresh because they are database-backed; the browser frontend continues using its own localStorage.

NOT IMPLEMENTED: LLMs, extraction, agent orchestration, MCP, external integrations, automated decisions/actions, approval flows, routines, graph/tree UI, fuzzy deduplication, multi-user isolation.

## Documentation checked

- [Official Python client](https://github.com/FalkorDB/falkordb-py): `FalkorDB.select_graph`, `Graph.query`, `Graph.ro_query`.
- [FalkorDB constraints](https://docs.falkordb.com/commands/graph.constraint-create): unique identity constraints and operational readiness.
- [Cypher functions](https://docs.falkordb.com/cypher/functions): `properties`, `nodes`, `relationships`, timestamps and path projections.
- [Docker persistence](https://docs.falkordb.com/operations/durability/persistence): named volume at the database data directory.

All query forms used here were additionally exercised against the local FalkorDB instance.
