# Process Family Studio 2.0

An end-to-end **local process-modeling application**: describe a process, inspect a real BPMN diagram, derive contextual variants, validate behavior, simulate execution, evolve the reference model, and recover previous work.

The interface is a canvas-first modeling workbench, not a dashboard mockup. It uses the real bpmn-js modeler/viewer and interoperable non-executable BPMN 2.0 XML.

## Start

1. Install Python 3.10+ if needed. Node.js 22.13+ is needed only to rebuild the frontend or run frontend tests.
2. Double-click **start.cmd** on Windows, or run `python backend/server.py` from this directory.
3. Open **http://localhost:8765**. The prebuilt frontend is included, so ordinary use needs no npm installation.
4. Open **Model settings** to configure your existing API endpoint, exact model name and key. Choose **OpenAI-compatible**, enter the base URL ending before `/chat/completions`, save, then test the connection. A remote endpoint must use HTTPS. This machine has no preconfigured model credentials.
5. Choose **From description → Natural language**, write or edit your own description, generate, review the diagram and source evidence, and select **Create this process family**.

For fully offline operation, choose **Structured language**. Every activity and gateway is compiled from the current text. Example workflows are optional starting points and never substitute for your input. Changing text invalidates its previous preview. Reopening From description uses the family's saved original input; manual diagram changes are not reverse-translated into prose. Regeneration creates a separate family, preserving existing variants and history.

## What is delivered

- Natural-language graph generation through a configurable Ollama or OpenAI-compatible endpoint; bounded validator-guided repair; explicit failures, not canned fallback diagrams.
- Source-linked activities: exact supporting excerpts, checked offsets, generation provenance, and warnings when a task changes after generation. Evidence presence does not prove business interpretation.
- Structured offline compiler with nested exclusive choices and parallel blocks, task types and role/swimlane ownership.
- Direct visual editing, task type/name/documentation inspector, readable zoom/pan, fit overview, guarded automatic layout in a Web Worker, BPMN/SVG export.
- Visual ordered recipes for INSERT, DELETE, MODIFY and MOVE; stable operation IDs, preview before saving, contextual metadata, duplicate/edit support and read-only derived views.
- Base-change impact preview, explicit conflict repair, optimistic base and variant versions, base history, audit records, recoverable variant deletion and JSON backup restoration.
- Structural checks, bounded token-state soundness analysis, deadlock counterexamples, interactive simulation with parallel synchronization and exportable traces.
- Family-wide release checks with a reproducible SHA-256 manifest fingerprint and validated backup export.
- SQLite WAL persistence, commit-before-success transactions, additive schema migrations, consistent database backup/integrity tooling, bounded requests and loopback security headers.

## Verify / develop

```powershell
python -m unittest discover -s backend -p "test_*.py"
cd frontend
npm ci
npm test
npm run build
```

Backend: **48 tests**. Frontend/interoperability: **10 tests**. The frontend build is split into modules without chunk-size warnings. Python has no third-party runtime dependencies. Development frontend: `npm run dev`, with the Python server running separately.

The backend tests include a local fake model HTTP server to verify transport contracts and changed-description forwarding. No real paid model inference was performed in this environment; connect and test your endpoint in the app.

## Operational use

Family JSON exports contain base XML, recipes, contexts, source provenance, historical bases, audit entries and recoverable deleted variants. Restore imports into a new family without overwriting existing work. JSON imports are bounded to 10 MB. For large workspaces or complete backups:

```powershell
python backend/manage.py check
python backend/manage.py backup outputs/workspace-backup.sqlite3
```

`STUDIO_DB` selects the SQLite path; `STUDIO_PORT` selects the loopback port. Environment-based model configuration is documented in `docs/MODEL_SETUP.md`. Keys entered in the UI remain in server memory and reset on restart; they are never included in model exports, status responses or backups.

## Supported scope

One acyclic process, one start/end, task/user/service/manual/business-rule/send/receive activities, exclusive and parallel split/join gateways, sequence flows, simple lanes and documentation. Cycles, executable imports, timers, boundary events, subprocesses, nested lanes, multi-pool collaborations and business-expression execution are explicitly unsupported. Context metadata describes variants; it is not a regulatory rule engine or feature-constraint solver.

This release is for trusted, single-user, local process engineering and academic presentation. It does not include organizational authentication, collaboration, public hosting or a production BPM engine. Exported BPMN is `isExecutable=false`; Camunda execution needs engine-specific implementation work. The validation fingerprint identifies evaluated artifacts; it is not a digital signature or regulatory certificate.

## Documentation and samples

- `docs/ENGINEERING_REVIEW.md`: findings and remediation
- `docs/PROJECT_REPORT.md`: architecture, algorithms and research mapping
- `docs/MODEL_SETUP.md`: endpoint configuration and troubleshooting
- `docs/USER_GUIDE.md`: end-to-end workflow
- `docs/API.md`: API contracts and error codes
- `docs/VALIDATION.md`: test and browser evidence, with verification limits
- `docs/PRESENTATION_GUIDE.md`: final-project demonstration and viva
- `samples/*-family.json`: three restorable families, each with a real variant

Keep bpmn.io attribution visible. Third-party licenses are included under `docs/third-party-licenses/`. No affiliation with Camunda, MIT or any university is implied.
