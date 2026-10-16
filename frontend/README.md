# ORBIT frontend — Phases 01–02

A responsive, browser-local React workspace with five original SVG bot identities, bot creation, editable settings, per-bot conversations and persistent storage. No AI responses or backend integrations are simulated.

## Run

From this directory:

```powershell
npm install
npm run dev
```

Open http://127.0.0.1:5173. Local chat requires no backend. The Graph View and Simple View buttons require the real ORBIT API on port 8001 and FalkorDB; see the [root README](../README.md) for startup and optional explicit seed instructions.

## Check

```powershell
npm run build
npm test
npx playwright test
```

Browser tests use installed Microsoft Edge; start the development server first. Tests cover creation, avatar and settings edits, message entry, independent histories, reload persistence, clearing, search and mobile navigation. Screenshots are written to `test-results/`.

## Structure

- `src.jsx`: workspace, accessible creation/clear dialogs, bot settings and chat components.
- `src/Avatar.jsx`: original scalable character illustrations.
- `src/services.js`: versioned storage boundary, validation and message creation API boundary.
- `style.css`: responsive layouts, character animation and reduced-motion support.

Workspace data stays under `orbit.workspace.v1` in localStorage, scoped to browser and origin. Clearing browser data removes it. Storage failures are surfaced; invalid saved data is not silently overwritten. Notifications are only a saved preference. Instructions are retained for later integration. No secrets should be placed in local storage.

The prior frontend source and styles are retained as `src.pathlock.jsx.bak` and `style.pathlock.css.bak`. The ORBIT backend is under `backend/orbit`; older PathLock backend and demo files remain separate.

Phase 02 graph files are under `src/graph/`: shared API service and types, workspace, network/tree canvas, Dagre projection and inspector. `npm run typecheck` checks these TypeScript modules. `npm run test:graph` starts isolated API/Vite servers and verifies both modes against a real temporary FalkorDB graph (Docker must be running). The normal `npx playwright test` command keeps the original chat suite separate.

FalkorDB persistence and graph visualization are implemented. Model connection, extraction, orchestration, tools, scheduling and integrations remain planned. Local chat storage is not automatically synchronized to the graph.
