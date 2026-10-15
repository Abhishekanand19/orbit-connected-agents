# ORBIT — Phase 1

A responsive, browser-local React workspace with five original SVG bot identities, bot creation, editable settings, per-bot conversations and persistent storage. No AI responses or backend integrations are simulated.

## Run

From this directory:

```powershell
npm install
npm run dev
```

Open http://127.0.0.1:5173. No backend, AWS credentials or database are required.

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

The prior frontend source and styles are retained as `src.pathlock.jsx.bak` and `style.pathlock.css.bak`. The existing backend and root demo scripts remain the earlier PathLock project; use this directory's commands to run ORBIT.

Later phases: model connection, backend persistence/FalkorDB, orchestration, tools, scheduling and integrations. None are implemented here.
