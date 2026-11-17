# Explainable Generation and Lifecycle Management of BPMN Process Families

## 1. Problem, scope and project contribution

Organizations maintain related processes for countries, products and customer segments. Keeping each as a separate diagram duplicates common behavior and makes changes difficult to propagate consistently. A configurable reference model and explicit variant changes provide a more manageable representation.

This project implements an integrated workbench for authoring, configuring, analyzing, simulating and evolving those families. It combines a real BPMN editor, two description-generation paths, source traceability, graph transformations, bounded behavior analysis, persistence and recovery. Its contribution is the integrated software artifact and its verification, not a claim of a new formal modeling language or a general solution to natural-language understanding.

The deployment scope is a trusted local single-user application. Its semantic scope is one acyclic process, one start/end, common task types, exclusive/parallel gateways, sequence flows, simple lanes and documentation. It is not a production execution engine or a full BPMN conformance implementation.

## 2. Requirements and design decisions

| Requirement | Implementation | Why |
|---|---|---|
| Input-dependent generation | Structured compiler and configurable model API | Examples must not substitute for the current description |
| Reviewable interpretation | Source quotes, assumptions, preview and accept step | A structurally valid AI output may still misread business meaning |
| Standard diagrams | bpmn-js and BPMN XML with DI | Avoid approximate custom BPMN symbols and proprietary output |
| Explicit variability | Ordered INSERT/DELETE/MODIFY/MOVE recipes | Differences remain inspectable instead of duplicated diagrams |
| Correctness feedback | Structure checks and bounded token-state exploration | Reject obvious graph errors and expose behavioral deadlocks |
| Evolution | Base revisions, change-impact preview and conflict repair | A removed target must not silently map to another activity |
| Reliability | Commit-before-response transactions and optimistic versions | Prevent false save acknowledgments and lost updates |
| Recovery | Drafts, history, trash, JSON restore and SQLite backup | Export alone is not a complete recovery workflow |
| Reproducibility | Manifest hashes and test evidence | Reviewers need to know which artifacts were evaluated |

## 3. Architecture

The browser owns interaction, diagram layout/rendering and token visualization. It calls a same-origin loopback HTTP API. The API delegates input validation and workflows to the application service, graph operations to the engine, model requests to a provider adapter, and persistence to SQLite.

| Module | Responsibility |
|---|---|
| `backend/engine.py` | Structured compiler, graph checks, BPMN parsing/serialization, recipe derivation, analysis and source maps |
| `backend/generation.py` | Provider contracts, structured graph prompting, exact quote validation and one repair attempt |
| `backend/service.py` | Creation, previews, saves, variants, restore, release checks and import workflows |
| `backend/store.py` | Additive migrations, SQLite transactions, snapshots, audit and backup serialization |
| `backend/validation.py` | Request/recipe/context constraints and typed errors |
| `backend/server.py` | Bounded loopback HTTP handling, host/origin checks, security headers and request IDs |
| `frontend/bpmn-types.js` | Explicit mapping between lowercase XML names and capitalized metamodel types |
| `frontend/layout.worker.js` | Official layout engine isolated from the UI thread |
| `frontend/simulation.js` | Testable token semantics, including multiplicity |
| `frontend/src.js` | Workbench, inspector, visual recipes, previews, history, model configuration and recovery |

The backend has no third-party runtime dependencies. The locked frontend dependencies and a prebuilt distribution are included. SQLite uses WAL mode; write workflows begin immediate transactions. The API returns only after transaction commit. Separate base revisions and variant versions detect stale edits.

## 4. Description generation and explainability

### Structured compilation

A recursive compiler reads one activity per line. `if/else/endif` emits an exclusive split and merge. `parallel/branch/endparallel` emits a fork and synchronizing join. Blocks can nest. Typed activity prefixes select task/user/service/manual/business-rule/send/receive elements. Optional role brackets create lane ownership. The compiler maps activity names to their exact source positions.

### Natural-language generation

The current description is submitted to an explicitly configured Ollama or OpenAI-compatible endpoint. The prompt requests a constrained JSON graph and supporting exact quotes for every activity. It does not request code execution. Returned data is parsed, structurally validated, linked to verified source offsets, and behaviorally analyzed. One repair request can include validator diagnostics. A second invalid response fails without saving a family. There is no canned fallback or automatic substitution of a sample.

The UI shows the preview and requires acceptance before persistence. A changed description invalidates the preview. Exact quote matching rejects fabricated citations but cannot prove semantic entailment; an overly broad quote can still support a poor interpretation. Human review remains essential. When a task's name/type later changes, the inspector warns that its original evidence needs rechecking.

Provider keys stay in server memory, are omitted from public status responses, and never enter backups. The configured remote endpoint must use HTTPS and redirects are rejected. Tests exercise real transport against a local fixture server. No external model was configured during delivery, so model accuracy and latency are not empirically established here.

## 5. Variability and evolution algorithms

A family stores a reference graph and a set of contextual recipes. Derivation copies the base, then applies operations in order. INSERT splits a single outgoing connection. DELETE removes a single-in/single-out activity and bridges its neighbors. MOVE removes and reinserts an activity at an allowed destination. MODIFY changes a label. Final structural validation rejects invalid results. Explicit operation IDs provide stable IDs for inserted activities.

Variants are re-derived against the latest base on load. A base-save preview identifies recipes whose targets no longer resolve. If saved, those recipes remain intact and visibly conflicted. Selecting one shows the base as a repair reference, letting the analyst replace targets and preview the repaired recipe. This is one-way derivation and explicit conflict repair; it is not bidirectional co-evolution or automatic semantic reconciliation.

History retains base snapshots. Restoring one creates a new revision. Variants use version-checked soft deletion and restoration. Backups preserve source provenance, contexts, recipes, deleted variants, historical base content and audit records; import assigns new workspace identities rather than overwriting existing families.

## 6. Control-flow analysis and simulation

Structural validation checks types, IDs, start/end counts, degrees, reachability and acyclicity. Forward and reverse traversal identify disconnected or non-terminating regions. Kahn traversal detects cycles. This is linear in graph size, aside from small representation overheads.

A behavioral marking consists of token multiplicity on each sequence flow and the count of completed end events. Exclusive gateways choose one outgoing branch; parallel forks produce tokens on all outgoing branches, and parallel joins consume every incoming token together. State exploration tracks distinct markings and predecessor transitions. A failed terminal state can yield a counterexample path.

A sound result requires complete exploration, a single completion with no residual tokens, no deadlocks and no dead activities. Exploration is bounded to 10,000 states and three seconds per diagram. Incomplete checks never count as sound. Family checking has an additional overall budget and reports uncompleted models rather than silently passing them.

The browser simulator uses matching token semantics and locks modeling during a run. It is an educational control-flow simulator: it does not execute services, evaluate data conditions, interact with customers or enforce regulations.

## 7. Diagram quality and interoperability

The actual bpmn-js modeler handles editing and XML interchange. Generated diagrams have non-executable BPMN semantics and DI geometry. Automatic layout runs in a Worker and verifies that every supported semantic element still has diagram representation. If layout cannot preserve coverage, retained valid geometry is used. Simple lanes have a deterministic fallback layout. The UI starts at a readable zoom, with explicit overview and pan controls.

Tests parse all three generated samples using bpmn-moddle and check semantic/DI references, including lane representation. They also check that automatic layout preserves the original semantic IDs. This supports interchange confidence, not OMG conformance certification or a claim that all external BPMN files are accepted.

## 8. Validation identity

Family validation produces a manifest containing the base revision and canonical graph hash, active variant IDs/versions, recipe/context hashes, analyzer identity and state limit. A SHA-256 digest of that manifest is the validation fingerprint. Repeated checks over unchanged artifacts reproduce it; a changed recipe or base alters it. It is not a signature, authenticated attestation or regulatory certificate.

## 9. Evaluation

48 backend tests and 10 frontend/interoperability tests pass. They cover malformed inputs, nested graphs, parallel synchronization, explicit deadlocks, immutable derivation, concurrent saves, stale versions, rollback, backups, migrations, generation contracts, exact source evidence and reproducible hashes. Browser checks exercise rewritten descriptions, stale-preview invalidation, visual recipes, comparisons, source-linked inspection, persistent editing, family validation and completed simulations.

The evaluation does not include independent participants, a real industrial dataset, a live model-quality benchmark, adversarial penetration testing, full BPMN execution, multi-user load or a Camunda engine deployment. These are explicitly separated from verified results.

## 10. Research foundations and limits

- **La Rosa, van der Aalst, Dumas and Milani (2017), Business Process Variability Modeling: A Survey.** ACM Computing Surveys 50(1), Article 2. [DOI](https://doi.org/10.1145/3041957). Provides the variability taxonomy and motivates comparing customizable-model approaches; it does not establish superiority of this implementation.
- **Hallerbach, Bauer and Reichert (2010), Capturing Variability in Business Process Models: The Provop Approach.** [DOI](https://doi.org/10.1002/smr.491). Informs the reference-plus-operations representation. This project implements a limited operation set, not the complete Provop framework.
- **Ayora, Torres, Weber, Reichert and Pelechano (2015), VIVACE.** [DOI](https://doi.org/10.1016/j.infsof.2014.05.009). Supports lifecycle-based assessment. Modeling, configuration, local simulation and one-way evolution are distinguished from production enactment.
- **Ayora, Torres, de la Vara and Pelechano (2016), Variability management in process families through change patterns.** Information and Software Technology 74, 86–104. [DOI](https://doi.org/10.1016/j.infsof.2016.01.007). Motivates explicit repeated changes and correctness checks. The paper's ten patterns and empirical reductions are not reproduced or claimed here.
- **ProMoAI: Process Modeling with Generative AI (IJCAI 2024).** [Proceedings paper](https://www.ijcai.org/proceedings/2024/1014.pdf). Demonstrates that text-to-process generation and interactive refinement are established research directions. Our JSON graph plus validation pipeline is a different implementation; we do not claim ProMoAI's POWL-based guarantees.
- **BPMN Assistant: An LLM-Based Approach to Business Process Modeling (2025 preprint).** [Author preprint](https://arxiv.org/abs/2509.24592). Relevant to language-driven modeling/editing and structured representations. No benchmark results from that work are adopted as results for this project.
- **OMG BPMN 2.0.2.** [Standard](https://www.omg.org/spec/BPMN/). Basis for element naming and interchange. [bpmn-js walkthrough](https://bpmn.io/toolkit/bpmn-js/walkthrough/) and the [layout project](https://github.com/bpmn-io/bpmn-auto-layout) document the editor and layout integration.

A defensible future study would compare generated graphs with independently authored reference models, measure activity/flow/role accuracy and semantic omissions, assess source-quote quality, and run analyst usability tasks. Those results must be collected rather than inferred from a passing unit-test suite.
