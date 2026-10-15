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

