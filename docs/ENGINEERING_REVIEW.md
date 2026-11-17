# Engineering and process-modeling review

## Release assessment

The original implementation demonstrated the core concept, but lacked several reliability and usability properties needed for regular local use. Version 2 addresses the concrete findings below. It remains deliberately a local single-user modeling product, not a public enterprise deployment or complete BPMN engine.

| Finding | Consequence | Implemented remediation |
|---|---|---|
| HTTP success could precede commit | Client could believe an uncommitted save succeeded | Application service returns only after transaction context commits; rollback and durability tests |
| Variant saves lacked independent version checks | Concurrent recipe edits could overwrite each other | Base revision plus variant version checks; serialized SQLite writes |
| Conflicted variants could not be selected | Users could see a conflict but not repair its recipe | Open conflict view using base canvas; editable recipe targets; preview and repair workflow |
| Delete was permanent | Accidental removal lost configuration work | Soft deletion, versioned restore and history trash |
| JSON backup had no import path | Exported artifacts were not a recovery workflow | Validated, transactional restore into a new family; historical snapshots, source metadata and audit preservation |
| Recipe insert IDs depended on array position | Reordering could break references to inserted tasks | Explicit stable operation IDs, retained through reorder/edit |
| Derived views used an editable modeler | Unsaved changes could masquerade as a derived variant | Separate read-only viewer for variants and simulation |
| Basic rank layout caused poor routing | Diagrams could be difficult to read | Official bpmn-auto-layout in a Worker, geometry coverage checks, editable retained fallback and readable zoom/pan |
| Editor/semantic type capitalization mismatch | Inspector, modeling rules and base simulation could fail | Central type adapter, actual moddle-object integration tests and browser checks |
| Replacement rule assumed the wrong command context | Task-type change could fail partway | Rule uses documented installed handler's `newData`; regression checks and browser replacement verification |
| Draft debounce could lose the latest edit on navigation | Recovery copy might trail the canvas | Explicit draft flush before leaving, revision-tagged recovery and stale-revision notice |
| Unsupported XML semantics could be ignored | Analyzer could claim checks over an incomplete interpretation | Namespace/global-ID validation and explicit rejection of unsupported executable details |
| Generation was limited to a formal language | Users could mistake line-to-task compilation for prose understanding | Separate model-backed natural-language mode, explicit configuration and no canned fallback |
| Generated activities had no rationale | Business reviewers could not inspect grounding | Exact source quotes and offsets, provenance and stale-evidence warnings |
| Validation reports lacked artifact identity | It was unclear which exact family was evaluated | Stable graph/recipe/version manifest with SHA-256 fingerprint |
| Product UI exposed raw recipes as the primary flow | Business users had to manipulate JSON | Visual operation cards, context fields, inspector and preview; JSON remains an advanced option |

## What still requires organizational work

Authentication/RBAC, remote multi-user deployment, tenant isolation, approvals, external monitoring, legal/data governance, execution-engine integration and independent usability testing have not been implemented. Those are deployment/product programs rather than labels that can be applied to this local release. Full BPMN semantics, semantic correctness of AI interpretations, and arbitrary natural-language accuracy are not claimed.
